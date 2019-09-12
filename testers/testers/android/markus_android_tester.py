import subprocess
import os
import glob
import xml.etree.ElementTree as eTree
from testers.markus_tester import MarkusTester, MarkusTest, iMarkusTestError

class MarkusAndroidTest(MarkusTest):
    def __init__(self, tester, result, feedback_open=None):
        self._test_name = result['name']
        self.status = result['status']
        self.message = result['message']
        super().__init__(tester, feedback_open)

    @property
    def test_name(self):
        return self._test_name

    @MarkusTest.run_decorator
    def run(self):
        if self.status == "success":
            return self.passed(message=self.message)
        elif self.status == "failure":
            return self.failed(message=self.message)
        else:
            return self.error(message=self.message)

class MarkusAndroidTester(MarkusTester):

    CACHE_DIRNAME='.m2'

    def __init__(self, specs, test_class=MarkusAndroidTest):
        cache_dir = os.path.join(specs['env_loc'], self.CACHE_DIRNAME)
        if not os.path.isdir(cache_dir):
            cache_dir = os.path.join(os.getcwd(), self.CACHE_DIRNAME)
        self.maven_opts = f"-Dmaven.repo.local={cache_dir}"
        test_cases = specs.get('test_data', 'maven_test_cases', default='')
        self.maven_test_cases = f"-Dtest={test_cases}"
        self.show_traceback = specs.get('test_data', 'show_traceback')
        super().__init__(specs, test_class=test_class)

    def _parse_junitxml(self, xml_filename):
        """
        Parse pytest results written to the file named
        xml_filename and yield a hash containing result data
        for each testcase.
        """
        tree = eTree.parse(xml_filename)
        root = tree.getroot()
        for testcase in root.iterfind('testcase'):
            result = {}
            classname = testcase.attrib['classname']    
            testname = testcase.attrib['name']
            result['name'] = '{}.{}'.format(classname, testname)
            result['time'] = float(testcase.attrib.get('time', 0))
            failure = testcase.find('failure')
            if failure is not None:
                result['status'] = 'failure'
                if self.show_traceback:
                    result['message'] = failure.text
                else:
                    failure_type = failure.attrib.get('type', '')
                    failure_message = failure.attrib.get('message', '')
                    result['message'] = f'{failure_type}: {failure_message}'
            else:
                result['status'] = 'success'
                result['message'] = ''
            yield result

    def run_android_tests(self):
        results = []
        this_dir = os.getcwd()
        env = {**os.environ, 'MAVEN_OPTS': self.maven_opts}
        cmd = ['mvn', 'test', self.maven_test_cases]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, env=env)
        for xml_filename in glob.iglob(os.path.join(os.getcwd(), 'target', 'surefire-reports', 'TEST*.xml')):
            for result in self._parse_junitxml(xml_filename):
                yield result

    @MarkusTester.run_decorator
    def run(self):
        try:
            results = self.run_android_tests()
        except subprocess.CalledProcessError as e:
            msg = (e.stdout or '' + e.stderr or '') or str(e)
            raise MarkusTestError(msg) from e
        with self.open_feedback() as feedback_open:
            for result in results:
                test = self.test_class(self, result, feedback_open)
                print(test.run(), flush=True)
