# Copyright 2022 Memgraph Ltd.
#
# Use of this software is governed by the Business Source License
# included in the file licenses/BSL.txt; by using this file, you agree to be bound by the terms of the Business Source
# License, and you may not use this file except in compliance with the Business Source License.
#
# As of the Change Date specified in that file, in accordance with
# the Business Source License, use of this software will be governed
# by the Apache License, Version 2.0, included in the file
# licenses/APL.txt.

import typing

import mgclient


def execute_and_fetch_all(cursor: mgclient.Cursor, query: str, params: dict = {}) -> typing.List[tuple]:
    cursor.execute(query, params)
    return cursor.fetchall()


def connect(**kwargs) -> mgclient.Connection:
    connection = mgclient.connect(**kwargs)
    connection.autocommit = True
    return connection


def safe_execute(function, *args):
    try:
        function(*args)
    except:
        pass


# NOTE: Repeated execution because it can fail if Raft server is not up
def add_coordinator(cursor, query):
    for _ in range(10):
        try:
            execute_and_fetch_all(cursor, query)
            return True
        except Exception:
            pass
    return False
