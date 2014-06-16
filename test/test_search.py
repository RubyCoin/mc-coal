import fix_dev_path  # noqa

from base_test import BaseTest

import main
import models
import patterns
import search

from test_api import ALL_LOG_LINES


class SearchTest(BaseTest):
    APPLICATION = main.application

    def setUp(self):
        super(SearchTest, self).setUp()
        self.server = models.Server.create()
        self.log_lines = []
        for line in ALL_LOG_LINES:
            self.log_lines.append(models.LogLine.create(self.server, line, 'America/Chicago'))

    def test_add_log_lines(self):
        search.add_log_lines(self.log_lines)
        results, number_found, cursor = search.search_log_lines('gumptionthomas')
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)

    def test_search_log_lines(self):
        results, number_found, cursor = search.search_log_lines('gumptionthomas')
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('info')
        self.assertEqual(10, len(results))
        self.assertEqual(10, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('vesicular')
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('yo')
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines(patterns.CONNECTION_TAG)
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        results, number_found, cursor = search.search_log_lines(patterns.SERVER_TAG)
        self.assertEqual(5, len(results))
        self.assertEqual(5, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('2012-10-15')
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('username:gumptionthomas tags:{0}'.format(patterns.LOGIN_TAG))
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)

    def test_search_log_lines_multi_server(self):
        self.server2 = models.Server.create()
        self.log_lines2 = []
        for line in ALL_LOG_LINES:
            self.log_lines2.append(models.LogLine.create(self.server2, line, 'America/Chicago'))
        results, number_found, cursor = search.search_log_lines('gumptionthomas')
        self.assertEqual(8, len(results))
        self.assertEqual(8, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('info')
        self.assertEqual(20, len(results))
        self.assertEqual(20, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('vesicular')
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('yo')
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines(patterns.CONNECTION_TAG)
        self.assertEqual(8, len(results))
        self.assertEqual(8, number_found)
        results, number_found, cursor = search.search_log_lines(patterns.SERVER_TAG)
        self.assertEqual(10, len(results))
        self.assertEqual(10, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('2012-10-15')
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('username:gumptionthomas tags:{0}'.format(patterns.LOGIN_TAG))
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)

        results, number_found, cursor = search.search_log_lines('gumptionthomas', server_key=self.server.key)
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('info', server_key=self.server.key)
        self.assertEqual(10, len(results))
        self.assertEqual(10, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('vesicular', server_key=self.server.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('yo', server_key=self.server.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines(patterns.CONNECTION_TAG, server_key=self.server.key)
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        results, number_found, cursor = search.search_log_lines(patterns.SERVER_TAG, server_key=self.server.key)
        self.assertEqual(5, len(results))
        self.assertEqual(5, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('2012-10-15', server_key=self.server.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('username:gumptionthomas tags:{0}'.format(patterns.LOGIN_TAG), server_key=self.server.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)

        results, number_found, cursor = search.search_log_lines('gumptionthomas', server_key=self.server2.key)
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('info', server_key=self.server2.key)
        self.assertEqual(10, len(results))
        self.assertEqual(10, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('vesicular', server_key=self.server2.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('yo', server_key=self.server2.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines(patterns.CONNECTION_TAG, server_key=self.server2.key)
        self.assertEqual(4, len(results))
        self.assertEqual(4, number_found)
        results, number_found, cursor = search.search_log_lines(patterns.SERVER_TAG, server_key=self.server2.key)
        self.assertEqual(5, len(results))
        self.assertEqual(5, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('2012-10-15', server_key=self.server2.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_log_lines('username:gumptionthomas tags:{0}'.format(patterns.LOGIN_TAG), server_key=self.server2.key)
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)

    def test_remove_log_lines(self):
        results, number_found, cursor = search.search_log_lines('info', limit=20)
        self.assertEqual(10, len(results))
        self.assertEqual(10, number_found)
        self.assertIsNone(cursor)
        for result in results:
            result.key.delete()
        results, number_found, cursor = search.search_log_lines('info')
        self.assertEqual(0, len(results))
        self.assertEqual(0, number_found)
        self.assertIsNone(cursor)

    def test_search_players(self):
        results, number_found, cursor = search.search_players('gumptionthomas')
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_players('vesicular')
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)

    def test_search_server_players(self):
        results, number_found, cursor = search.search_players('gumptionthomas')
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_players('vesicular')
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)

    def test_search_server_players_multi_server(self):
        self.server2 = models.Server.create()
        self.log_lines2 = []
        for line in ALL_LOG_LINES:
            self.log_lines2.append(models.LogLine.create(self.server2, line, 'America/Chicago'))
        results, number_found, cursor = search.search_players('gumptionthomas')
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_players('vesicular')
        self.assertEqual(2, len(results))
        self.assertEqual(2, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_players('gumptionthomas', server_key=self.server.key)
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_players('vesicular', server_key=self.server.key)
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_players('gumptionthomas', server_key=self.server2.key)
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)
        results, number_found, cursor = search.search_players('vesicular', server_key=self.server2.key)
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)

    def test_remove_players(self):
        results, number_found, cursor = search.search_players('gumptionthomas')
        self.assertEqual(1, len(results))
        self.assertEqual(1, number_found)
        self.assertIsNone(cursor)
        for result in results:
            result.key.delete()
        results, number_found, cursor = search.search_players('gumptionthomas')
        self.assertEqual(0, len(results))
        self.assertEqual(0, number_found)
        self.assertIsNone(cursor)

    def test_cursor(self):
        results, number_found, cursor = search.search_log_lines('info', limit=6)
        self.assertEqual(6, len(results))
        self.assertEqual(10, number_found)
        self.assertIsNotNone(cursor)
        results, number_found, cursor = search.search_log_lines('info', cursor=cursor)
        self.assertEqual(4, len(results))
        self.assertEqual(10, number_found)
        self.assertIsNone(cursor)
