import enum
import json
import subprocess


class UAMResult:
    """
    A test result from uam.
    """

    class Status(enum.Enum):
        PASS = 1
        FAIL = 2
        ERROR = 3

    def __init__(self, file_name, class_name, test_name, status, description=None, message=None, trace=None):
        self.file_name = file_name
        self.class_name = class_name
        self.test_name = test_name
        self.status = status
        self.description = description
        self.message = message
        self.trace = trace

    @property
    def test_title(self):
        title = self.test_name if not self.class_name else '{}.{}'.format(self.class_name, self.test_name)
        if self.description:
            title += ' ({})'.format(self.description)
        return title


class UAMTester:
    """
    A base wrapper class to run a uam tester (https://github.com/ProjectAT/uam).
    """

    ERROR_MGSG = {
        'uam_error': 'UAM framework error: {}',
        'no_result': 'UAM framework error: no result file generated',
        'timeout': 'Tests timed out'
    }
    GLOBAL_TIMEOUT_DEFAULT = 30
    TEST_TIMEOUT_DEFAULT = 10

    def __init__(self, path_to_uam, path_to_tests, test_points, global_timeout=GLOBAL_TIMEOUT_DEFAULT,
                 test_timeout=TEST_TIMEOUT_DEFAULT, result_filename='result.json'):
        """
        Initializes the basic parameters to run a uam tester.
        :param path_to_uam: The path to the uam installation.
        :param path_to_tests: The path to the tests.
        :param test_points: A dict of test files to run and points assigned: the keys are test file names, the values
                            are dicts of test functions (or test classes) to points; if a test function/class is
                            missing, it is assigned a default of 1 point (use an empty dict for all 1s).
        :param global_timeout: The time limit to run all tests.
        :param test_timeout: The time limit to run a single test.
        :param result_filename: The file name of the output.
        """
        self.path_to_uam = path_to_uam
        self.path_to_tests = path_to_tests
        self.test_points = test_points
        self.global_timeout = global_timeout
        self.test_timeout = test_timeout
        self.result_filename = result_filename

    def generate_results(self):
        """
        Runs the tester and generates the result file.
        """
        raise NotImplementedError

    def collect_results(self):
        """
        Collects results from a tester result file.
        :return: A list of results.
        """
        results = []
        with open(self.result_filename) as result_file:
            result = json.load(result_file)
            for file_class, test_result in result['results'].items():
                file_class_names = file_class.split('.')
                if len(file_class_names) == 1:  # Class (java) or file (python)
                    file_name = file_class_names[0]
                    class_name = file_class_names[0] if file_name.istitle() else None
                else:  # file.Class (python)
                    file_name = file_class_names[0]
                    class_name = file_class_names[1]
                if 'passes' in test_result:
                    for test_id, test_desc in test_result['passes'].items():
                        test_name = test_id.rpartition(':')[2] if ':' in test_id else test_id.rpartition('.')[2]
                        results.append(
                            UAMResult(file_name, class_name, test_name, status=UAMResult.Status.PASS,
                                      description=test_desc))
                if 'failures' in test_result:
                    for test_id, test_stack in test_result['failures'].items():
                        test_name = test_id.rpartition(':')[2] if ':' in test_id else test_id.rpartition('.')[2]
                        results.append(
                            UAMResult(file_name, class_name, test_name, status=UAMResult.Status.FAIL,
                                      description=test_stack['description'], message=test_stack['message'],
                                      trace=test_stack['details']))
                if 'errors' in test_result:
                    for test_id, test_stack in test_result['errors'].items():
                        test_name = test_id.rpartition(':')[2] if ':' in test_id else test_id.rpartition('.')[2]
                        results.append(
                            UAMResult(file_name, class_name, test_name, status=UAMResult.Status.ERROR,
                                      description=test_stack['description'], message=test_stack['message']))
        return results

    def get_test_points(self, result, file_ext):
        """
        Gets the available total points for a uam test result based on the test specifications.
        :param result: A uam test result.
        :param file_ext: The test file extension.
        :return: The total available points
        """
        test_file = '{}.{}'.format(result.file_name, file_ext)
        test_points = self.test_points[test_file]
        return test_points.get(result.test_name, test_points.get(result.class_name, 1))

    def run(self):
        """
        Runs the tester.
        :return A list of test results.
        """
        try:
            self.generate_results()
            return self.collect_results()
        except subprocess.TimeoutExpired:
            raise Exception(self.ERROR_MGSG['timeout'])
        except subprocess.CalledProcessError as e:
            raise Exception(self.ERROR_MGSG['uam_error'].format(e.stdout))
        except OSError:
            raise Exception(self.ERROR_MGSG['no_result'])
