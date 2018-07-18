"""
Test google API
"""
from __future__ import unicode_literals

import json
import sys
import unittest
from io import BytesIO

from googleapiclient.http import HttpMockSequence
from mock import patch
import six
from six.moves import range  # use the range function introduced in python 3
from tubular.google_api import DriveApi

# For info about this file, see tubular/tests/discovery-drive.json.README.rst
DISCOVERY_DRIVE_RESPONSE_FILE = 'tubular/tests/discovery-drive.json'


class TestDriveApi(unittest.TestCase):
    """
    Test the DriveApi class.
    """
    def setUp(self):
        with open(DISCOVERY_DRIVE_RESPONSE_FILE, 'r') as f:
            self.mock_discovery_response_content = f.read()

    @classmethod
    def _http_mock_sequence_retry(cls):
        """
        Returns a tuple, for use in http mock sequences, which represents a response from google suggesting to retry.
        """
        return (
            {'status': '403'},
            json.dumps({
                "error": {
                    "errors": [
                        {
                            "domain": "usageLimits",
                            "reason": "userRateLimitExceeded",
                            "message": "User Rate Limit Exceeded",
                        }
                    ],
                    "code": 403,
                    "message": "User Rate Limit Exceeded",
                }
            }).encode('utf-8'),
        )

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_create_file_success(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Test normal case for uploading a file.
        """
        fake_file_id = 'fake-file-id'
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
            # Then, a request is made to upload the file.
            ({'status': '200'}, '{{"id": "{}"}}'.format(fake_file_id)),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        response = test_client.create_file_in_folder(
            'fake-folder-id',
            'Fake Filename',
            BytesIO('fake file contents'.encode('ascii')),
            'text/plain',
        )
        assert response == fake_file_id

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    # pylint: disable=unused-argument
    def test_create_file_retry_success(self, mock_from_service_account_file):
        """
        Test rate limit and retry during file upload.
        """
        fake_file_id = 'fake-file-id'
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
            # Then, a request is made to upload the file while rate limiting was activated.  This should cause a retry.
            self._http_mock_sequence_retry(),
            # Finally, success.
            ({'status': '200'}, '{{"id": "{}"}}'.format(fake_file_id)),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        response = test_client.create_file_in_folder(
            'fake-folder-id',
            'Fake Filename',
            BytesIO('fake file contents'.encode('ascii')),
            'text/plain',
        )
        # There is no need to explicitly check if the call was retried because
        # the response value cannot possibly contain fake_file_id otherwise,
        # since it was only passed in the last response.
        assert response == fake_file_id

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_delete_file_success(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Test normal case for deleting files.
        """
        fake_file_ids = ['fake-file-id1', 'fake-file-id2']
        batch_response = b'''--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+1>

HTTP/1.1 204 OK
ETag: "etag/pony"\r\n\r\n

--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+2>

HTTP/1.1 204 OK
ETag: "etag/sheep"\r\n\r\n
--batch_foobarbaz--'''
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
            # Then, a request is made to delete files.
            ({'status': '200', 'content-type': 'multipart/mixed; boundary="batch_foobarbaz"'}, batch_response),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        if sys.version_info < (3, 4):
            # This is a simple smoke-test without checking the output because
            # python 2 doesn't support assertLogs.
            test_client.delete_files(fake_file_ids)
        else:
            # This is the full test case, which only runs under python 3.
            with self.assertLogs(level='INFO') as captured_logs:  # pylint: disable=no-member
                test_client.delete_files(fake_file_ids)
            assert sum(
                'Successfully deleted file.' in msg
                for msg in captured_logs.output
            ) == 2

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_delete_file_with_nonexistent_file(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Test case for deleting files where some are nonexistent.
        """
        fake_file_id_non_existent = 'fake-file-id1'
        fake_file_id_exists = 'fake-file-id2'
        batch_response = b'''--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+1>

HTTP/1.1 404 NOT FOUND
Content-Type: application/json
Content-length: 266
ETag: "etag/pony"\r\n\r\n{
 "error": {
  "errors": [
   {
    "domain": "global",
    "reason": "notFound",
    "message": "File not found: fake-file-id1.",
    "locationType": "parameter",
    "location": "fileId"
   }
  ],
  "code": 404,
  "message": "File not found: fake-file-id1."
 }
}

--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+2>

HTTP/1.1 204 OK
ETag: "etag/sheep"\r\n\r\n
--batch_foobarbaz--'''
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
            # Then, a request is made to delete files.
            ({'status': '200', 'content-type': 'multipart/mixed; boundary="batch_foobarbaz"'}, batch_response),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        if sys.version_info < (3, 4):
            # This is a simple smoke-test without checking the output because
            # python 2 doesn't support assertLogs.
            test_client.delete_files([fake_file_id_non_existent, fake_file_id_exists])
        else:
            # This is the full test case, which only runs under python 3.
            with self.assertLogs(level='INFO') as captured_logs:  # pylint: disable=no-member
                test_client.delete_files([fake_file_id_non_existent, fake_file_id_exists])
            assert any(
                'File not found: {file_id}'.format(file_id=fake_file_id_non_existent) in msg
                for msg in captured_logs.output
            )
            assert any(
                'Successfully deleted file.' in msg
                for msg in captured_logs.output
            )

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_list_subfolders_one_page(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Simple case where subfolders are requested, and the response contains one page.
        """
        fake_files = [
            {'id': 'fake-folder-id-{}'.format(idx), 'name': 'fake-folder-name-{}'.format(idx)}
            for idx in range(10)
        ]
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            (
                {'status': '200'},
                self.mock_discovery_response_content,
            ),
            # Then, a request is made to list files.
            (
                {'status': '200', 'content-type': 'application/json'},
                json.dumps({'files': fake_files}).encode('utf-8'),
            ),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        response = test_client.list_subfolders('fake-folder-id')
        six.assertCountEqual(self, response, fake_files)

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_list_subfolders_two_page(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Subfolders are requested, but the response is paginated.
        """
        fake_files = [
            {'id': 'fake-folder-id-{}'.format(idx), 'name': 'fake-folder-name-{}'.format(idx)}
            for idx in range(10)
        ]
        fake_files_part_1 = fake_files[:7]
        fake_files_part_2 = fake_files[7:]
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            (
                {'status': '200'},
                self.mock_discovery_response_content,
            ),
            # Then, a request is made to list files.  The response contains a nextPageToken suggesting there are more
            # pages.
            (
                {'status': '200', 'content-type': 'application/json'},
                json.dumps({'files': fake_files_part_1, 'nextPageToken': 'fake-next-page-token'}).encode('utf-8'),
            ),
            # Finally, a second list request is made.  This time, no nextPageToken is present in the response,
            # suggesting there are no more pages.
            (
                {'status': '200', 'content-type': 'application/json'},
                json.dumps({'files': fake_files_part_2}).encode('utf-8'),
            ),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        response = test_client.list_subfolders('fake-folder-id')
        six.assertCountEqual(self, response, fake_files)

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_list_subfolders_retry(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Subfolders are requested, but there is rate limiting causing a retry.
        """
        fake_files = [
            {'id': 'fake-folder-id-{}'.format(idx), 'name': 'fake-folder-name-{}'.format(idx)}
            for idx in range(10)
        ]
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            (
                {'status': '200'},
                self.mock_discovery_response_content),
            # Then, a request is made to list files, but the response suggests to retry.
            self._http_mock_sequence_retry(),
            # Finally, the request is retried, and the response is OK.
            (
                {'status': '200', 'content-type': 'application/json'},
                json.dumps({'files': fake_files}).encode('utf-8'),
            ),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        response = test_client.list_subfolders('fake-folder-id')
        six.assertCountEqual(self, response, fake_files)

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_comment_files_success(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Test normal case for commenting on files.
        """
        fake_file_ids = ['fake-file-id0', 'fake-file-id1']
        batch_response = b'''--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+0>

HTTP/1.1 204 OK
ETag: "etag/pony"\r\n\r\n{"id": "fake-comment-id0"}

--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+1>

HTTP/1.1 204 OK
ETag: "etag/sheep"\r\n\r\n{"id": "fake-comment-id1"}
--batch_foobarbaz--'''
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
            # Then, a request is made to add comments to the files.
            ({'status': '200', 'content-type': 'multipart/mixed; boundary="batch_foobarbaz"'}, batch_response),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        resp = test_client.create_comments_for_files(fake_file_ids, 'some comment message')
        six.assertCountEqual(
            self,
            resp,
            {
                'fake-file-id0': {'id': 'fake-comment-id0'},
                'fake-file-id1': {'id': 'fake-comment-id1'},
            },
        )

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_comment_files_batching(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Test commenting on more files than the google API batch limit (100).
        """
        num_files = 150  # >100
        fake_file_ids = ['fake-file-id{}'.format(n) for n in range(0, num_files)]
        batch_response_0 = '\n'.join(
            '''--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+{idx}>

HTTP/1.1 204 OK
ETag: "etag/pony{idx}"\r\n\r\n{{"id": "fake-comment-id{idx}"}}
'''.format(idx=n)
            for n in range(0, 100)
        )
        batch_response_0 += '--batch_foobarbaz--'
        batch_response_1 = '\n'.join(
            '''--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+{idx}>

HTTP/1.1 204 OK
ETag: "etag/pony{idx}"\r\n\r\n{{"id": "fake-comment-id{idx}"}}
'''.format(idx=n)
            for n in range(0, 50)
        )
        batch_response_1 += '--batch_foobarbaz--'
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
            # Then, a request is made to add comments to the files, first batch. Return 100 results.
            ({'status': '200', 'content-type': 'multipart/mixed; boundary="batch_foobarbaz"'}, batch_response_0),
            # Then, a request is made to add comments to the files, second batch. Return the last 50 results.
            ({'status': '200', 'content-type': 'multipart/mixed; boundary="batch_foobarbaz"'}, batch_response_1),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        resp = test_client.create_comments_for_files(fake_file_ids, 'some comment message')
        six.assertCountEqual(
            self,
            resp,
            {
                'fake-file-id{}'.format(n): {'id': 'fake-comment-id{}'.format(n)}
                for n in range(0, num_files)
            },
        )

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_comment_files_with_nonexistent_file(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Test case for commenting on files, where some files are nonexistent.
        """
        fake_file_ids = ['fake-file-id0', 'fake-file-id1']
        batch_response = b'''--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+0>

HTTP/1.1 404 NOT FOUND
Content-Type: application/json
Content-length: 266
ETag: "etag/pony"\r\n\r\n{
 "error": {
  "errors": [
   {
    "domain": "global",
    "reason": "notFound",
    "message": "File not found: fake-file-id0.",
    "locationType": "parameter",
    "location": "fileId"
   }
  ],
  "code": 404,
  "message": "File not found: fake-file-id0."
 }
}

--batch_foobarbaz
Content-Type: application/http
Content-Transfer-Encoding: binary
Content-ID: <response+1>

HTTP/1.1 204 OK
ETag: "etag/sheep"\r\n\r\n{"id": "fake-comment-id1"}
--batch_foobarbaz--'''
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
            # Then, a request is made to add comments to the files.
            ({'status': '200', 'content-type': 'multipart/mixed; boundary="batch_foobarbaz"'}, batch_response),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        resp = test_client.create_comments_for_files(fake_file_ids, 'some comment message')
        six.assertCountEqual(
            self,
            resp,
            {
                'fake-file-id0': {
                    "error": {
                        "errors": [
                            {
                                "domain": "global",
                                "reason": "notFound",
                                "message": "File not found: fake-file-id0.",
                                "locationType": "parameter",
                                "location": "fileId"
                            }
                        ],
                        "code": 404,
                        "message": "File not found: fake-file-id0."
                    }
                },
                'fake-file-id1': {'id': 'fake-comment-id1'},
            },
        )

    @patch('tubular.google_api.service_account.Credentials.from_service_account_file', return_value=None)
    def test_comment_files_with_duplicate_file(self, mock_from_service_account_file):  # pylint: disable=unused-argument
        """
        Test case for duplicate file IDs.
        """
        fake_file_ids = ['fake-file-id0', 'fake-file-id1', 'fake-file-id0']
        http_mock_sequence = HttpMockSequence([
            # First, a request is made to the discovery API to construct a client object for Drive.
            ({'status': '200'}, self.mock_discovery_response_content),
        ])
        test_client = DriveApi('non-existent-secrets.json', http=http_mock_sequence)
        with self.assertRaises(ValueError):
            test_client.create_comments_for_files(fake_file_ids, 'some comment message')