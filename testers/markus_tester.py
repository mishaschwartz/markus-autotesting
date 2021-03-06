import collections
import contextlib
import enum
import json
import os
import subprocess
from xml.sax import saxutils
import sys


class MarkusTestSpecs(collections.MutableMapping):

    # special keys
    MATRIX_KEY = 'matrix'
    MATRIX_NODATA_KEY = 'nodata'
    MATRIX_NONTEST_KEY = 'extra'
    FEEDBACK_FILE_KEY = 'feedback_file'
    DATA_FILES_SEPARATOR = ','

    def __init__(self, path_to_specs=None):
        if path_to_specs is None:  # try to find specs automagically
            path_to_specs = sys.executable.replace('venvs', 'specs').replace('bin/python3', 'specs.json')
        with open(path_to_specs, 'r') as specs_open:
            self._specs = json.loads(specs_open.read())
        if MarkusTestSpecs.MATRIX_KEY not in self._specs:
            self._specs[MarkusTestSpecs.MATRIX_KEY] = {}
        if MarkusTestSpecs.FEEDBACK_FILE_KEY not in self._specs:
            self._specs[MarkusTestSpecs.FEEDBACK_FILE_KEY] = None

    def _setitem(self, key, value):
        self._specs[key] = value

    def _set_points(self, _, value):
        """
        SPECS['points'] = {'test1': {'data1': 11, 'data2': 12}, 'test2': {'data1': 21, 'data2': 22}}
        Assigns points to the passed tests and datasets, creating them if they don't exist yet.
        """
        for test, data_files in value.items():
            if test in self.matrix:
                for data_file, points in data_files.items():
                    self.matrix[test][data_file] = points
            else:
                self.matrix[test] = data_files

    def _set_test_points(self, _, value):
        """
        SPECS['test_points'] = {'test1': 1, 'test2': 2}
        Assigns points to all datasets of the passed tests, creating the tests if they don't exist yet.
        """
        for test, points in value.items():
            data_files = self.matrix.setdefault(test, {MarkusTestSpecs.MATRIX_NODATA_KEY: {}})
            for data_file in data_files:
                if data_file == MarkusTestSpecs.MATRIX_NONTEST_KEY:
                    continue
                self.matrix[test][data_file] = points

    def _set_data_points(self, _, value):
        """
        SPECS['data_points'] = {'data1': 1, 'data2': 2}
        Assigns points to all existing tests that use the passed datasets, does nothing for tests that don't use them.
        """
        for test in self.matrix:
            for data_file, points in value.items():
                if data_file not in self.matrix[test]:
                    continue
                self.matrix[test][data_file] = points

    def _set_all_points(self, _, points):
        """
        SPECS['all_points'] = points
        Assigns points to all existing tests and datasets.
        """
        for test, data_files in self.matrix.items():
            for data_file in data_files:
                if data_file == MarkusTestSpecs.MATRIX_NONTEST_KEY:
                    continue
                self.matrix[test][data_file] = points

    def __setitem__(self, key, value):
        switch = {'points': self._set_points, 'test_points': self._set_test_points,
                  'data_points': self._set_data_points, 'all_points': self._set_all_points}
        setter = switch.get(key, self._setitem)
        setter(key, value)

    def __getitem__(self, key):
        return self._specs[key]

    def __delitem__(self, key):
        del self._specs[key]

    def __iter__(self):
        return iter(self._specs)

    def __len__(self):
        return len(self._specs)

    @property
    def matrix(self):
        return self[MarkusTestSpecs.MATRIX_KEY]

    @property
    def feedback_file(self):
        return self[MarkusTestSpecs.FEEDBACK_FILE_KEY]

    @property
    def tests(self):
        return self.matrix.keys()


class MarkusTest:

    class Status(enum.Enum):
        PASS = 'pass'
        PARTIAL = 'partial'
        FAIL = 'fail'
        ERROR = 'error'
        ERROR_ALL = 'error_all'

    def __init__(self, tester, test_file, data_files, points, test_extra, feedback_open=None):
        self.tester = tester
        self.test_file = test_file  # TODO Is really a file or a more generic test the base unit here?
        self.data_files = data_files
        self.points = points  # TODO Use a default or disable if not set?
        if isinstance(self.points, collections.abc.Mapping):
            self.points_total = sum(self.points.values())
        else:
            self.points_total = self.points
        if self.points_total <= 0:
            raise ValueError('The test total points must be > 0')
        self.test_extra = test_extra
        self.feedback_open = feedback_open

    @property
    def test_name(self):
        return os.path.splitext(self.test_file)[0]

    @property
    def data_name(self):
        return MarkusTestSpecs.DATA_FILES_SEPARATOR.join([os.path.splitext(data_file)[0]
                                                          for data_file in self.data_files])

    @property
    def test_data_name(self):
        if self.data_name == MarkusTestSpecs.MATRIX_NODATA_KEY:
            return self.test_name
        else:
            return '{} + {}'.format(self.test_name, self.data_name)

    @staticmethod
    def format_result(test_name, status, output, points_earned, points_total):
        """
        Formats a test result as expected by Markus.
        :param test_name: The test name
        :param status: A member of MarkusTest.Status.
        :param output: The test output.
        :param points_earned: The points earned by the test, must be a float >= 0 (can be greater than the test total
                              points when assigning bonus points).
        :param points_total: The total points the test could earn, must be a float >= 0.
        :return The formatted test result.
        """
        if points_total < 0:
            raise ValueError('The test total points must be >= 0')
        if points_earned < 0:
            raise ValueError('The test points earned must be >= 0')
        output_escaped = saxutils.escape(output.replace('\x00', ''), entities={"'": '&apos;'})
        return '''
<test>
  <name>{}</name>
  <input></input>
  <expected></expected>
  <actual>{}</actual>
  <marks_earned>{}</marks_earned>
  <marks_total>{}</marks_total>
  <status>{}</status>
</test>'''.format(test_name, output_escaped, points_earned, points_total, status.value)

    def format(self, status, output, points_earned):
        """
        Formats the result of this test as expected by Markus.
        :param status: A member of MarkusTest.Status.
        :param output: The test output.
        :param points_earned: The points earned by the test, must be a float >= 0 (can be greater than the test total
                              points when assigning bonus points).
        :return The formatted test result.
        """
        return MarkusTest.format_result(self.test_data_name, status, output, points_earned, self.points_total)

    def add_feedback(self, status, feedback='', oracle_solution=None, test_solution=None):
        """
        Adds the feedback of this test to the feedback file.
        :param status: A member of MarkusTest.Status.
        :param feedback: The feedback, can be None.
        :param oracle_solution: The expected solution, can be None.
        :param test_solution: The test solution, can be None.
        """
        # TODO Reconcile with format: return both, or print both
        if self.feedback_open is None:
            raise ValueError('No feedback file enabled')
        self.feedback_open.write('========== {}: {} ==========\n\n'.format(self.test_data_name, status.value.upper()))
        if feedback:
            self.feedback_open.write('## Feedback: {}\n\n'.format(feedback))
        if status != self.Status.PASS:
            if oracle_solution:
                self.feedback_open.write('## Expected Solution:\n\n')
                self.feedback_open.write(oracle_solution)
            if test_solution:
                self.feedback_open.write('## Your Solution:\n\n')
                self.feedback_open.write(test_solution)
        self.feedback_open.write('\n')

    def passed_with_bonus(self, points_bonus, message=''):
        """
        Passes this test earning bonus points in addition to the test total points. If a feedback file is enabled, adds
        feedback to it.
        :param points_bonus: The bonus points, must be a float >= 0.
        :param message: An optional message, will be shown as test output.
        :return The formatted passed test.
        """
        if points_bonus < 0:
            raise ValueError('The test bonus points must be >= 0')
        result = self.format(status=self.Status.PASS, output=message, points_earned=self.points_total+points_bonus)
        if self.feedback_open:
            self.add_feedback(status=self.Status.PASS)
        return result

    def passed(self, message=''):
        """
        Passes this test earning the test total points. If a feedback file is enabled, adds feedback to it.
        :param message: An optional message, will be shown as test output.
        :return The formatted passed test.
        """
        result = self.format(status=self.Status.PASS, output=message, points_earned=self.points_total)
        if self.feedback_open:
            self.add_feedback(status=self.Status.PASS)
        return result

    def partially_passed(self, points_earned, message, oracle_solution=None, test_solution=None):
        """
        Partially passes this test with some points earned. If a feedback file is enabled, adds feedback to it.
        :param points_earned: The points earned by the test, must be a float > 0 and < the test total points.
        :param message: The message explaining why the test was not fully passed, will be shown as test output.
        :param oracle_solution: The optional correct solution to be added to the feedback file.
        :param test_solution: The optional student solution to be added to the feedback file.
        :return The formatted partially passed test.
        """
        if points_earned <= 0:
            raise ValueError('The test points earned must be > 0')
        if points_earned >= self.points_total:
            raise ValueError('The test points earned must be < the test total points')
        result = self.format(status=self.Status.PARTIAL, output=message, points_earned=points_earned)
        if self.feedback_open:
            self.add_feedback(status=self.Status.PARTIAL, feedback=message, oracle_solution=oracle_solution,
                              test_solution=test_solution)
        return result

    def failed(self, message, oracle_solution=None, test_solution=None):
        """
        Fails this test with 0 points earned. If a feedback file is enabled, adds feedback to it.
        :param message: The failure message, will be shown as test output.
        :param oracle_solution: The optional correct solution to be added to the feedback file.
        :param test_solution: The optional student solution to be added to the feedback file.
        :return The formatted failed test.
        """
        result = self.format(status=self.Status.FAIL, output=message, points_earned=0)
        if self.feedback_open:
            self.add_feedback(status=self.Status.FAIL, feedback=message, oracle_solution=oracle_solution,
                              test_solution=test_solution)
        return result

    def done(self, points_earned, message='', oracle_solution=None, test_solution=None):
        """
        Passes, partially passes or fails this test depending on the points earned. If the points are <= 0 this test is
        failed with 0 points earned, if the points are >= test total points this test is passed earning the test total
        points (plus the possible bonus), otherwise this test is partially passed. If a feedback file is enabled, adds
        feedback to it.
        :param points_earned: The points earned by the test.
        :param message: The optional message explaining the test outcome, will be shown as test output.
        :param oracle_solution: The optional correct solution to be added to the feedback file.
        :param test_solution: The optional student solution to be added to the feedback file.
        :return The formatted test.
        """
        if points_earned <= 0:
            return self.failed(message, oracle_solution, test_solution)
        elif points_earned == self.points_total:
            return self.passed(message)
        elif points_earned > self.points_total:
            points_bonus = points_earned - self.points_total
            return self.passed_with_bonus(points_bonus, message)
        else:
            return self.partially_passed(points_earned, message, oracle_solution, test_solution)

    def error(self, message):
        """
        Err this test. If a feedback file is enabled, adds feedback to it.
        :param message: The error message, will be shown as test output.
        :return The formatted erred test.
        """
        result = self.format(status=self.Status.ERROR, output=message, points_earned=0)
        if self.feedback_open:
            self.add_feedback(status=self.Status.ERROR, feedback=message)
        return result

    def run(self):
        """
        Runs this test.
        :return The formatted test.
        """
        raise NotImplementedError


class MarkusTester:

    def __init__(self, specs, test_class=MarkusTest):
        self.specs = specs
        self.test_class = test_class

    @staticmethod
    def error_all(message, points_total=0):
        """
        Err all tests of this tester with a single message.
        :param message: The error message.
        :param points_total: The total points the tests could earn, must be a float >= 0.
        :return The formatted erred tests.
        """
        return MarkusTest.format_result(test_name='All tests', status=MarkusTest.Status.ERROR_ALL, output=message,
                                        points_earned=0, points_total=points_total)

    def upload_svn_feedback(self, markus_root_url, repo_name, assignment_name, svn_file_name, svn_user, svn_password,
                            commit_message):
        markus_server_url, _, markus_instance = markus_root_url.rpartition('/')
        repo_url = '/'.join([markus_server_url, 'svn', markus_instance, repo_name])
        svn_co_command = ['svn', 'co', '--username', svn_user, '--password', svn_password, repo_url]
        subprocess.run(svn_co_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        repo_path = os.path.join(repo_name, assignment_name, svn_file_name)
        previous_file = os.path.isfile(repo_path)
        cp_command = ['cp', '-f', self.specs.feedback_file, repo_path]
        subprocess.run(cp_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not previous_file:
            svn_add_command = ['svn', 'add', repo_path]
            subprocess.run(svn_add_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        svn_ci_command = ['svn', 'ci', '--username', svn_user, '--password', svn_password, '-m', commit_message,
                          repo_path]
        subprocess.run(svn_ci_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def run(self):
        try:
            with contextlib.ExitStack() as stack:
                feedback_open = (stack.enter_context(open(self.specs.feedback_file, 'w'))
                                 if self.specs.feedback_file is not None
                                 else None)
                for test_file in sorted(self.specs.tests):
                    test_extra = self.specs.matrix[test_file].get(MarkusTestSpecs.MATRIX_NONTEST_KEY, {})
                    for data_files in sorted(self.specs.matrix[test_file].keys()):
                        if data_files == MarkusTestSpecs.MATRIX_NONTEST_KEY:
                            continue
                        points = self.specs.matrix[test_file][data_files]
                        if MarkusTestSpecs.DATA_FILES_SEPARATOR in data_files:
                            data_files = data_files.split(MarkusTestSpecs.DATA_FILES_SEPARATOR)
                        else:
                            data_files = [data_files]
                        test = self.test_class(self, test_file, data_files, points, test_extra, feedback_open)
                        xml = test.run()
                        print(xml)
        except Exception as e:
            print(MarkusTester.error_all(message=str(e)))
