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

import os
import shutil
import sys
import tempfile

import interactive_mg_runner
import pytest
from common import connect, execute_and_fetch_all, safe_execute
from mg_utils import (
    mg_sleep_and_assert,
    mg_sleep_and_assert_any_function,
    mg_sleep_and_assert_collection,
)

interactive_mg_runner.SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
interactive_mg_runner.PROJECT_DIR = os.path.normpath(
    os.path.join(interactive_mg_runner.SCRIPT_DIR, "..", "..", "..", "..")
)
interactive_mg_runner.BUILD_DIR = os.path.normpath(os.path.join(interactive_mg_runner.PROJECT_DIR, "build"))
interactive_mg_runner.MEMGRAPH_BINARY = os.path.normpath(os.path.join(interactive_mg_runner.BUILD_DIR, "memgraph"))

TEMP_DIR = tempfile.TemporaryDirectory().name

MEMGRAPH_INSTANCES_DESCRIPTION = {
    "instance_1": {
        "args": [
            "--experimental-enabled=high-availability",
            "--bolt-port",
            "7687",
            "--log-level",
            "TRACE",
            "--coordinator-server-port",
            "10011",
        ],
        "log_file": "instance_1.log",
        "data_directory": f"{TEMP_DIR}/instance_1",
        "setup_queries": [],
    },
    "instance_2": {
        "args": [
            "--experimental-enabled=high-availability",
            "--bolt-port",
            "7688",
            "--log-level",
            "TRACE",
            "--coordinator-server-port",
            "10012",
        ],
        "log_file": "instance_2.log",
        "data_directory": f"{TEMP_DIR}/instance_2",
        "setup_queries": [],
    },
    "instance_3": {
        "args": [
            "--experimental-enabled=high-availability",
            "--bolt-port",
            "7689",
            "--log-level",
            "TRACE",
            "--coordinator-server-port",
            "10013",
        ],
        "log_file": "instance_3.log",
        "data_directory": f"{TEMP_DIR}/instance_3",
        "setup_queries": [],
    },
    "coordinator_1": {
        "args": [
            "--experimental-enabled=high-availability",
            "--bolt-port",
            "7690",
            "--log-level=TRACE",
            "--raft-server-id=1",
            "--raft-server-port=10111",
        ],
        "log_file": "coordinator1.log",
        "setup_queries": [],
    },
    "coordinator_2": {
        "args": [
            "--experimental-enabled=high-availability",
            "--bolt-port",
            "7691",
            "--log-level=TRACE",
            "--raft-server-id=2",
            "--raft-server-port=10112",
        ],
        "log_file": "coordinator2.log",
        "setup_queries": [],
    },
    "coordinator_3": {
        "args": [
            "--experimental-enabled=high-availability",
            "--bolt-port",
            "7692",
            "--log-level=TRACE",
            "--raft-server-id=3",
            "--raft-server-port=10113",
        ],
        "log_file": "coordinator3.log",
        "setup_queries": [
            "ADD COORDINATOR 1 ON '127.0.0.1:10111'",
            "ADD COORDINATOR 2 ON '127.0.0.1:10112'",
            "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.1:10001'",
            "REGISTER INSTANCE instance_2 ON '127.0.0.1:10012' WITH '127.0.0.1:10002'",
            "REGISTER INSTANCE instance_3 ON '127.0.0.1:10013' WITH '127.0.0.1:10003'",
            "SET INSTANCE instance_3 TO MAIN",
        ],
    },
}


def get_instances_description_no_setup():
    return {
        "instance_1": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7687",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10011",
            ],
            "log_file": "instance_1.log",
            "data_directory": f"{TEMP_DIR}/instance_1",
            "setup_queries": [],
        },
        "instance_2": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7688",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10012",
            ],
            "log_file": "instance_2.log",
            "data_directory": f"{TEMP_DIR}/instance_2",
            "setup_queries": [],
        },
        "instance_3": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7689",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10013",
            ],
            "log_file": "instance_3.log",
            "data_directory": f"{TEMP_DIR}/instance_3",
            "setup_queries": [],
        },
        "coordinator_1": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7690",
                "--log-level=TRACE",
                "--raft-server-id=1",
                "--raft-server-port=10111",
            ],
            "log_file": "coordinator1.log",
            "data_directory": f"{TEMP_DIR}/coordinator_1",
            "setup_queries": [],
        },
        "coordinator_2": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7691",
                "--log-level=TRACE",
                "--raft-server-id=2",
                "--raft-server-port=10112",
            ],
            "log_file": "coordinator2.log",
            "data_directory": f"{TEMP_DIR}/coordinator_2",
            "setup_queries": [],
        },
        "coordinator_3": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7692",
                "--log-level=TRACE",
                "--raft-server-id=3",
                "--raft-server-port=10113",
            ],
            "log_file": "coordinator3.log",
            "data_directory": f"{TEMP_DIR}/coordinator_3",
            "setup_queries": [],
        },
    }


def test_old_main_comes_back_on_new_leader_as_replica():
    # 1. Start all instances.
    # 2. Kill the main instance
    # 3. Kill the leader
    # 4. Start the old main instance
    # 5. Run SHOW INSTANCES on the new leader and check that the old main instance is registered as a replica
    # 6. Start again previous leader

    safe_execute(shutil.rmtree, TEMP_DIR)
    inner_instances_description = get_instances_description_no_setup()

    interactive_mg_runner.start_all(inner_instances_description)

    setup_queries = [
        "ADD COORDINATOR 1 ON '127.0.0.1:10111'",
        "ADD COORDINATOR 2 ON '127.0.0.1:10112'",
        "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.1:10001'",
        "REGISTER INSTANCE instance_2 ON '127.0.0.1:10012' WITH '127.0.0.1:10002'",
        "REGISTER INSTANCE instance_3 ON '127.0.0.1:10013' WITH '127.0.0.1:10003'",
        "SET INSTANCE instance_3 TO MAIN",
    ]
    coord_cursor_3 = connect(host="localhost", port=7692).cursor()
    for query in setup_queries:
        execute_and_fetch_all(coord_cursor_3, query)

    interactive_mg_runner.kill(inner_instances_description, "coordinator_3")
    interactive_mg_runner.kill(inner_instances_description, "instance_3")

    coord_cursor_1 = connect(host="localhost", port=7690).cursor()

    def show_instances_coord1():
        return sorted(list(execute_and_fetch_all(coord_cursor_1, "SHOW INSTANCES;")))

    coord_cursor_2 = connect(host="localhost", port=7691).cursor()

    def show_instances_coord2():
        return sorted(list(execute_and_fetch_all(coord_cursor_2, "SHOW INSTANCES;")))

    leader_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "127.0.0.1:10011", "up", "main"),
        ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
        ("instance_3", "", "127.0.0.1:10013", "down", "unknown"),
    ]
    mg_sleep_and_assert_any_function(leader_data, [show_instances_coord1, show_instances_coord2])

    follower_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "", "unknown", "main"),
        ("instance_2", "", "", "unknown", "replica"),
        ("instance_3", "", "", "unknown", "main"),  # TODO: (andi) Will become unknown.
    ]
    mg_sleep_and_assert_any_function(leader_data, [show_instances_coord1, show_instances_coord2])
    mg_sleep_and_assert_any_function(follower_data, [show_instances_coord1, show_instances_coord2])

    interactive_mg_runner.start(inner_instances_description, "instance_3")

    leader_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "127.0.0.1:10011", "up", "main"),
        ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
        ("instance_3", "", "127.0.0.1:10013", "up", "replica"),
    ]
    mg_sleep_and_assert_any_function(leader_data, [show_instances_coord1, show_instances_coord2])

    new_main_cursor = connect(host="localhost", port=7687).cursor()

    def show_replicas():
        return sorted(list(execute_and_fetch_all(new_main_cursor, "SHOW REPLICAS;")))

    replicas = [
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_3",
            "127.0.0.1:10003",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
    ]
    mg_sleep_and_assert_collection(replicas, show_replicas)

    execute_and_fetch_all(new_main_cursor, "CREATE (n:Node {name: 'node'})")

    replica_2_cursor = connect(host="localhost", port=7688).cursor()

    def get_vertex_count():
        return execute_and_fetch_all(replica_2_cursor, "MATCH (n) RETURN count(n)")[0][0]

    mg_sleep_and_assert(1, get_vertex_count)

    replica_3_cursor = connect(host="localhost", port=7689).cursor()

    def get_vertex_count():
        return execute_and_fetch_all(replica_3_cursor, "MATCH (n) RETURN count(n)")[0][0]

    mg_sleep_and_assert(1, get_vertex_count)

    interactive_mg_runner.start(inner_instances_description, "coordinator_3")


def test_distributed_automatic_failover():
    safe_execute(shutil.rmtree, TEMP_DIR)
    interactive_mg_runner.start_all(MEMGRAPH_INSTANCES_DESCRIPTION)

    main_cursor = connect(host="localhost", port=7689).cursor()
    expected_data_on_main = [
        (
            "instance_1",
            "127.0.0.1:10001",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
    ]

    def retrieve_data_show_replicas():
        return sorted(list(execute_and_fetch_all(main_cursor, "SHOW REPLICAS;")))

    mg_sleep_and_assert_collection(expected_data_on_main, retrieve_data_show_replicas)

    interactive_mg_runner.kill(MEMGRAPH_INSTANCES_DESCRIPTION, "instance_3")

    coord_cursor = connect(host="localhost", port=7692).cursor()

    def retrieve_data_show_repl_cluster():
        return sorted(list(execute_and_fetch_all(coord_cursor, "SHOW INSTANCES;")))

    expected_data_on_coord = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "127.0.0.1:10011", "up", "main"),
        ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
        ("instance_3", "", "127.0.0.1:10013", "down", "unknown"),
    ]

    mg_sleep_and_assert(expected_data_on_coord, retrieve_data_show_repl_cluster)

    new_main_cursor = connect(host="localhost", port=7687).cursor()

    def retrieve_data_show_replicas():
        return sorted(list(execute_and_fetch_all(new_main_cursor, "SHOW REPLICAS;")))

    expected_data_on_new_main = [
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_3",
            "127.0.0.1:10003",
            "sync",
            {"ts": 0, "behind": None, "status": "invalid"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "invalid"}},
        ),
    ]
    mg_sleep_and_assert_collection(expected_data_on_new_main, retrieve_data_show_replicas)

    interactive_mg_runner.start(MEMGRAPH_INSTANCES_DESCRIPTION, "instance_3")
    expected_data_on_new_main_old_alive = [
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_3",
            "127.0.0.1:10003",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
    ]

    mg_sleep_and_assert_collection(expected_data_on_new_main_old_alive, retrieve_data_show_replicas)


def test_distributed_automatic_failover_with_leadership_change():
    safe_execute(shutil.rmtree, TEMP_DIR)
    inner_instances_description = get_instances_description_no_setup()

    interactive_mg_runner.start_all(inner_instances_description)

    setup_queries = [
        "ADD COORDINATOR 1 ON '127.0.0.1:10111'",
        "ADD COORDINATOR 2 ON '127.0.0.1:10112'",
        "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.1:10001'",
        "REGISTER INSTANCE instance_2 ON '127.0.0.1:10012' WITH '127.0.0.1:10002'",
        "REGISTER INSTANCE instance_3 ON '127.0.0.1:10013' WITH '127.0.0.1:10003'",
        "SET INSTANCE instance_3 TO MAIN",
    ]
    coord_cursor_3 = connect(host="localhost", port=7692).cursor()
    for query in setup_queries:
        execute_and_fetch_all(coord_cursor_3, query)

    interactive_mg_runner.kill(inner_instances_description, "coordinator_3")
    interactive_mg_runner.kill(inner_instances_description, "instance_3")

    coord_cursor_1 = connect(host="localhost", port=7690).cursor()

    def show_instances_coord1():
        return sorted(list(execute_and_fetch_all(coord_cursor_1, "SHOW INSTANCES;")))

    coord_cursor_2 = connect(host="localhost", port=7691).cursor()

    def show_instances_coord2():
        return sorted(list(execute_and_fetch_all(coord_cursor_2, "SHOW INSTANCES;")))

    leader_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "127.0.0.1:10011", "up", "main"),
        ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
        ("instance_3", "", "127.0.0.1:10013", "down", "unknown"),
    ]
    mg_sleep_and_assert_any_function(leader_data, [show_instances_coord1, show_instances_coord2])

    follower_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "", "unknown", "main"),
        ("instance_2", "", "", "unknown", "replica"),
        ("instance_3", "", "", "unknown", "main"),  # TODO: (andi) Will become unknown.
    ]
    mg_sleep_and_assert_any_function(leader_data, [show_instances_coord1, show_instances_coord2])
    mg_sleep_and_assert_any_function(follower_data, [show_instances_coord1, show_instances_coord2])

    new_main_cursor = connect(host="localhost", port=7687).cursor()

    def retrieve_data_show_replicas():
        return sorted(list(execute_and_fetch_all(new_main_cursor, "SHOW REPLICAS;")))

    expected_data_on_new_main = [
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_3",
            "127.0.0.1:10003",
            "sync",
            {"ts": 0, "behind": None, "status": "invalid"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "invalid"}},
        ),
    ]
    mg_sleep_and_assert_collection(expected_data_on_new_main, retrieve_data_show_replicas)

    interactive_mg_runner.start(inner_instances_description, "instance_3")
    expected_data_on_new_main_old_alive = [
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_3",
            "127.0.0.1:10003",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
    ]

    mg_sleep_and_assert_collection(expected_data_on_new_main_old_alive, retrieve_data_show_replicas)

    interactive_mg_runner.start(inner_instances_description, "coordinator_3")


def test_no_leader_after_leader_and_follower_die():
    # 1. Register all but one replication instnce on the first leader.
    # 2. Kill the leader and a follower.
    # 3. Check that the remaining follower is not promoted to leader by trying to register remaining replication instance.

    safe_execute(shutil.rmtree, TEMP_DIR)

    interactive_mg_runner.start_all(MEMGRAPH_INSTANCES_DESCRIPTION)

    interactive_mg_runner.kill(MEMGRAPH_INSTANCES_DESCRIPTION, "coordinator_3")
    interactive_mg_runner.kill(MEMGRAPH_INSTANCES_DESCRIPTION, "coordinator_2")

    coord_cursor_1 = connect(host="localhost", port=7690).cursor()

    with pytest.raises(Exception) as e:
        execute_and_fetch_all(coord_cursor_1, "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.10001'")
        assert str(e) == "Couldn't register replica instance since coordinator is not a leader!"


def test_old_main_comes_back_on_new_leader_as_main():
    # 1. Start all instances.
    # 2. Kill all instances
    # 3. Kill the leader
    # 4. Start the old main instance
    # 5. Run SHOW INSTANCES on the new leader and check that the old main instance is main once again

    safe_execute(shutil.rmtree, TEMP_DIR)

    inner_memgraph_instances = get_instances_description_no_setup()
    interactive_mg_runner.start_all(inner_memgraph_instances)

    coord_cursor_3 = connect(host="localhost", port=7692).cursor()

    setup_queries = [
        "ADD COORDINATOR 1 ON '127.0.0.1:10111'",
        "ADD COORDINATOR 2 ON '127.0.0.1:10112'",
        "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.1:10001'",
        "REGISTER INSTANCE instance_2 ON '127.0.0.1:10012' WITH '127.0.0.1:10002'",
        "REGISTER INSTANCE instance_3 ON '127.0.0.1:10013' WITH '127.0.0.1:10003'",
        "SET INSTANCE instance_3 TO MAIN",
    ]

    for query in setup_queries:
        execute_and_fetch_all(coord_cursor_3, query)

    interactive_mg_runner.kill(inner_memgraph_instances, "instance_1")
    interactive_mg_runner.kill(inner_memgraph_instances, "instance_2")
    interactive_mg_runner.kill(inner_memgraph_instances, "instance_3")
    interactive_mg_runner.kill(inner_memgraph_instances, "coordinator_3")

    coord_cursor_1 = connect(host="localhost", port=7690).cursor()

    def show_instances_coord1():
        return sorted(list(execute_and_fetch_all(coord_cursor_1, "SHOW INSTANCES;")))

    coord_cursor_2 = connect(host="localhost", port=7691).cursor()

    def show_instances_coord2():
        return sorted(list(execute_and_fetch_all(coord_cursor_2, "SHOW INSTANCES;")))

    interactive_mg_runner.start(inner_memgraph_instances, "instance_3")

    leader_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "127.0.0.1:10011", "down", "unknown"),
        ("instance_2", "", "127.0.0.1:10012", "down", "unknown"),
        ("instance_3", "", "127.0.0.1:10013", "up", "main"),
    ]

    follower_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("instance_1", "", "", "unknown", "replica"),
        ("instance_2", "", "", "unknown", "replica"),
        ("instance_3", "", "", "unknown", "main"),
    ]
    mg_sleep_and_assert_any_function(leader_data, [show_instances_coord1, show_instances_coord2])
    mg_sleep_and_assert_any_function(follower_data, [show_instances_coord1, show_instances_coord2])

    interactive_mg_runner.start(inner_memgraph_instances, "instance_1")
    interactive_mg_runner.start(inner_memgraph_instances, "instance_2")

    new_main_cursor = connect(host="localhost", port=7689).cursor()

    def show_replicas():
        return sorted(list(execute_and_fetch_all(new_main_cursor, "SHOW REPLICAS;")))

    replicas = [
        (
            "instance_1",
            "127.0.0.1:10001",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 0, "behind": 0, "status": "ready"}},
        ),
    ]
    mg_sleep_and_assert_collection(replicas, show_replicas)

    execute_and_fetch_all(new_main_cursor, "CREATE (n:Node {name: 'node'})")

    replica_1_cursor = connect(host="localhost", port=7687).cursor()
    assert len(execute_and_fetch_all(replica_1_cursor, "MATCH (n) RETURN n;")) == 1

    replica_2_cursor = connect(host="localhost", port=7688).cursor()
    assert len(execute_and_fetch_all(replica_2_cursor, "MATCH (n) RETURN n;")) == 1

    interactive_mg_runner.start(inner_memgraph_instances, "coordinator_3")


def test_registering_4_coords():
    # Goal of this test is to assure registering of multiple coordinators in row works
    safe_execute(shutil.rmtree, TEMP_DIR)
    INSTANCES_DESCRIPTION = {
        "instance_1": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7687",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10011",
            ],
            "log_file": "instance_1.log",
            "data_directory": f"{TEMP_DIR}/instance_1",
            "setup_queries": [],
        },
        "instance_2": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7688",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10012",
            ],
            "log_file": "instance_2.log",
            "data_directory": f"{TEMP_DIR}/instance_2",
            "setup_queries": [],
        },
        "instance_3": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7689",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10013",
            ],
            "log_file": "instance_3.log",
            "data_directory": f"{TEMP_DIR}/instance_3",
            "setup_queries": [],
        },
        "coordinator_1": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7690",
                "--log-level=TRACE",
                "--raft-server-id=1",
                "--raft-server-port=10111",
            ],
            "log_file": "coordinator1.log",
            "setup_queries": [],
        },
        "coordinator_2": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7691",
                "--log-level=TRACE",
                "--raft-server-id=2",
                "--raft-server-port=10112",
            ],
            "log_file": "coordinator2.log",
            "setup_queries": [],
        },
        "coordinator_3": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7692",
                "--log-level=TRACE",
                "--raft-server-id=3",
                "--raft-server-port=10113",
            ],
            "log_file": "coordinator3.log",
            "setup_queries": [],
        },
        "coordinator_4": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7693",
                "--log-level=TRACE",
                "--raft-server-id=4",
                "--raft-server-port=10114",
            ],
            "log_file": "coordinator4.log",
            "setup_queries": [
                "ADD COORDINATOR 1 ON '127.0.0.1:10111';",
                "ADD COORDINATOR 2 ON '127.0.0.1:10112';",
                "ADD COORDINATOR 3 ON '127.0.0.1:10113';",
                "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.1:10001'",
                "REGISTER INSTANCE instance_2 ON '127.0.0.1:10012' WITH '127.0.0.1:10002'",
                "REGISTER INSTANCE instance_3 ON '127.0.0.1:10013' WITH '127.0.0.1:10003'",
                "SET INSTANCE instance_3 TO MAIN",
            ],
        },
    }

    interactive_mg_runner.start_all(INSTANCES_DESCRIPTION)

    coord_cursor = connect(host="localhost", port=7693).cursor()

    def retrieve_data_show_repl_cluster():
        return sorted(list(execute_and_fetch_all(coord_cursor, "SHOW INSTANCES;")))

    expected_data_on_coord = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("coordinator_4", "127.0.0.1:10114", "", "unknown", "coordinator"),
        ("instance_1", "", "127.0.0.1:10011", "up", "replica"),
        ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
        ("instance_3", "", "127.0.0.1:10013", "up", "main"),
    ]
    mg_sleep_and_assert(expected_data_on_coord, retrieve_data_show_repl_cluster)


def test_registering_coord_log_store():
    # Goal of this test is to assure registering a bunch of instances and de-registering works properly
    # w.r.t nuRaft log
    # 1. Start basic instances # 3 logs
    # 2. Check all is there
    # 3. Create 3 additional instances and add them to cluster # 3 logs -> 1st snapshot
    # 4. Check everything is there
    # 5. Set main # 1 log
    # 6. Check correct state
    # 7. Drop 2 new instances # 2 logs
    # 8. Check correct state
    # 9. Drop 1 new instance # 1 log -> 2nd snapshot
    # 10. Check correct state
    safe_execute(shutil.rmtree, TEMP_DIR)

    INSTANCES_DESCRIPTION = {
        "instance_1": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7687",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10011",
            ],
            "log_file": "instance_1.log",
            "data_directory": f"{TEMP_DIR}/instance_1",
            "setup_queries": [],
        },
        "instance_2": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7688",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10012",
            ],
            "log_file": "instance_2.log",
            "data_directory": f"{TEMP_DIR}/instance_2",
            "setup_queries": [],
        },
        "instance_3": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7689",
                "--log-level",
                "TRACE",
                "--coordinator-server-port",
                "10013",
            ],
            "log_file": "instance_3.log",
            "data_directory": f"{TEMP_DIR}/instance_3",
            "setup_queries": [],
        },
        "coordinator_1": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7690",
                "--log-level=TRACE",
                "--raft-server-id=1",
                "--raft-server-port=10111",
            ],
            "log_file": "coordinator1.log",
            "setup_queries": [],
        },
        "coordinator_2": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7691",
                "--log-level=TRACE",
                "--raft-server-id=2",
                "--raft-server-port=10112",
            ],
            "log_file": "coordinator2.log",
            "setup_queries": [],
        },
        "coordinator_3": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7692",
                "--log-level=TRACE",
                "--raft-server-id=3",
                "--raft-server-port=10113",
            ],
            "log_file": "coordinator3.log",
            "setup_queries": [],
        },
        "coordinator_4": {
            "args": [
                "--experimental-enabled=high-availability",
                "--bolt-port",
                "7693",
                "--log-level=TRACE",
                "--raft-server-id=4",
                "--raft-server-port=10114",
            ],
            "log_file": "coordinator4.log",
            "setup_queries": [
                "ADD COORDINATOR 1 ON '127.0.0.1:10111';",
                "ADD COORDINATOR 2 ON '127.0.0.1:10112';",
                "ADD COORDINATOR 3 ON '127.0.0.1:10113';",
                "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.1:10001'",
                "REGISTER INSTANCE instance_2 ON '127.0.0.1:10012' WITH '127.0.0.1:10002'",
                "REGISTER INSTANCE instance_3 ON '127.0.0.1:10013' WITH '127.0.0.1:10003'",
            ],
        },
    }
    assert "SET INSTANCE instance_3 TO MAIN" not in INSTANCES_DESCRIPTION["coordinator_4"]["setup_queries"]

    # 1
    interactive_mg_runner.start_all(INSTANCES_DESCRIPTION)

    # 2
    coord_cursor = connect(host="localhost", port=7693).cursor()

    def retrieve_data_show_repl_cluster():
        return sorted(list(execute_and_fetch_all(coord_cursor, "SHOW INSTANCES;")))

    coordinators = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
        ("coordinator_4", "127.0.0.1:10114", "", "unknown", "coordinator"),
    ]

    basic_instances = [
        ("instance_1", "", "127.0.0.1:10011", "up", "replica"),
        ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
        ("instance_3", "", "127.0.0.1:10013", "up", "replica"),
    ]

    expected_data_on_coord = []
    expected_data_on_coord.extend(coordinators)
    expected_data_on_coord.extend(basic_instances)

    mg_sleep_and_assert(expected_data_on_coord, retrieve_data_show_repl_cluster)

    # 3
    instances_ports_added = [10011, 10012, 10013]
    bolt_port_id = 7700
    coord_port_id = 10014

    additional_instances = []
    for i in range(4, 7):
        instance_name = f"instance_{i}"
        args_desc = [
            "--experimental-enabled=high-availability",
            "--log-level=TRACE",
        ]

        bolt_port = f"--bolt-port={bolt_port_id}"

        coord_server_port = f"--coordinator-server-port={coord_port_id}"

        args_desc.append(bolt_port)
        args_desc.append(coord_server_port)

        instance_description = {
            "args": args_desc,
            "log_file": f"instance_{i}.log",
            "data_directory": f"{TEMP_DIR}/instance_{i}",
            "setup_queries": [],
        }

        full_instance_desc = {instance_name: instance_description}
        interactive_mg_runner.start(full_instance_desc, instance_name)
        repl_port_id = coord_port_id - 10
        assert repl_port_id < 10011, "Wrong test setup, repl port must be smaller than smallest coord port id"

        execute_and_fetch_all(
            coord_cursor,
            f"REGISTER INSTANCE {instance_name} ON '127.0.0.1:{coord_port_id}' WITH '127.0.0.1:{repl_port_id}'",
        )

        additional_instances.append((f"{instance_name}", "", f"127.0.0.1:{coord_port_id}", "up", "replica"))
        instances_ports_added.append(coord_port_id)
        coord_port_id += 1
        bolt_port_id += 1

    # 4
    expected_data_on_coord.extend(additional_instances)

    mg_sleep_and_assert(expected_data_on_coord, retrieve_data_show_repl_cluster)

    # 5
    execute_and_fetch_all(coord_cursor, "SET INSTANCE instance_3 TO MAIN")

    # 6
    basic_instances.pop()
    basic_instances.append(("instance_3", "", "127.0.0.1:10013", "up", "main"))

    new_expected_data_on_coordinator = []

    new_expected_data_on_coordinator.extend(coordinators)
    new_expected_data_on_coordinator.extend(basic_instances)
    new_expected_data_on_coordinator.extend(additional_instances)

    mg_sleep_and_assert(new_expected_data_on_coordinator, retrieve_data_show_repl_cluster)

    # 7
    for i in range(6, 4, -1):
        execute_and_fetch_all(coord_cursor, f"UNREGISTER INSTANCE instance_{i};")
        additional_instances.pop()

    new_expected_data_on_coordinator = []
    new_expected_data_on_coordinator.extend(coordinators)
    new_expected_data_on_coordinator.extend(basic_instances)
    new_expected_data_on_coordinator.extend(additional_instances)

    # 8
    mg_sleep_and_assert(new_expected_data_on_coordinator, retrieve_data_show_repl_cluster)

    # 9

    new_expected_data_on_coordinator = []
    new_expected_data_on_coordinator.extend(coordinators)
    new_expected_data_on_coordinator.extend(basic_instances)

    execute_and_fetch_all(coord_cursor, f"UNREGISTER INSTANCE instance_4;")

    # 10
    mg_sleep_and_assert(new_expected_data_on_coordinator, retrieve_data_show_repl_cluster)


def test_multiple_failovers_in_row_no_leadership_change():
    # Goal of this test is to assure multiple failovers in row work without leadership change
    # 1. Start basic instances
    # 2. Check all is there
    # 3. Kill MAIN (instance_3)
    # 4. Expect failover (instance_1)
    # 5. Kill instance_1
    # 6. Expect failover instance_2
    # 7. Start instance_3
    # 8. Expect instance_3 and instance_2 (MAIN) up
    # 9. Kill instance_2
    # 10. Expect instance_3 MAIN
    # 11. Write some data on instance_3
    # 12. Start instance_2 and instance_1
    # 13. Expect instance_1 and instance2 to be up and cluster to have correct state
    # 13. Expect data to be replicated

    # 1
    inner_memgraph_instances = get_instances_description_no_setup()
    interactive_mg_runner.start_all(inner_memgraph_instances, keep_directories=False)

    coord_cursor_3 = connect(host="localhost", port=7692).cursor()

    setup_queries = [
        "ADD COORDINATOR 1 ON '127.0.0.1:10111'",
        "ADD COORDINATOR 2 ON '127.0.0.1:10112'",
        "REGISTER INSTANCE instance_1 ON '127.0.0.1:10011' WITH '127.0.0.1:10001'",
        "REGISTER INSTANCE instance_2 ON '127.0.0.1:10012' WITH '127.0.0.1:10002'",
        "REGISTER INSTANCE instance_3 ON '127.0.0.1:10013' WITH '127.0.0.1:10003'",
        "SET INSTANCE instance_3 TO MAIN",
    ]

    for query in setup_queries:
        execute_and_fetch_all(coord_cursor_3, query)

    # 2

    def get_func_show_instances(cursor):
        def show_instances_follower_coord():
            return sorted(list(execute_and_fetch_all(cursor, "SHOW INSTANCES;")))

        return show_instances_follower_coord

    coordinator_data = [
        ("coordinator_1", "127.0.0.1:10111", "", "unknown", "coordinator"),
        ("coordinator_2", "127.0.0.1:10112", "", "unknown", "coordinator"),
        ("coordinator_3", "127.0.0.1:10113", "", "unknown", "coordinator"),
    ]

    leader_data = []
    leader_data.extend(coordinator_data)
    leader_data.extend(
        [
            ("instance_1", "", "127.0.0.1:10011", "up", "replica"),
            ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
            ("instance_3", "", "127.0.0.1:10013", "up", "main"),
        ]
    )

    follower_data = []
    follower_data.extend(coordinator_data)
    follower_data.extend(
        [
            ("instance_1", "", "", "unknown", "replica"),
            ("instance_2", "", "", "unknown", "replica"),
            ("instance_3", "", "", "unknown", "main"),
        ]
    )

    coord_cursor_1 = connect(host="localhost", port=7690).cursor()
    coord_cursor_2 = connect(host="localhost", port=7691).cursor()

    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_1))
    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_2))
    mg_sleep_and_assert_collection(leader_data, get_func_show_instances(coord_cursor_3))

    # 3

    interactive_mg_runner.kill(inner_memgraph_instances, "instance_3")

    # 4

    leader_data = []
    leader_data.extend(coordinator_data)
    leader_data.extend(
        [
            ("instance_1", "", "127.0.0.1:10011", "up", "main"),
            ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
            ("instance_3", "", "127.0.0.1:10013", "down", "unknown"),
        ]
    )

    follower_data = []
    follower_data.extend(coordinator_data)
    follower_data.extend(
        [
            ("instance_1", "", "", "unknown", "main"),
            ("instance_2", "", "", "unknown", "replica"),
            (
                "instance_3",
                "",
                "",
                "unknown",
                "main",
            ),  # TODO(antoniofilipovic) change to unknown after PR with transitions
        ]
    )

    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_1))
    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_2))
    mg_sleep_and_assert_collection(leader_data, get_func_show_instances(coord_cursor_3))

    # 5
    interactive_mg_runner.kill(inner_memgraph_instances, "instance_1")

    # 6
    leader_data = []
    leader_data.extend(coordinator_data)
    leader_data.extend(
        [
            ("instance_1", "", "127.0.0.1:10011", "down", "unknown"),
            ("instance_2", "", "127.0.0.1:10012", "up", "main"),
            ("instance_3", "", "127.0.0.1:10013", "down", "unknown"),
        ]
    )

    follower_data = []
    follower_data.extend(coordinator_data)
    follower_data.extend(
        [
            ("instance_1", "", "", "unknown", "main"),
            ("instance_2", "", "", "unknown", "main"),  # TODO(antoniofilipovic) change to unknown
            ("instance_3", "", "", "unknown", "main"),  # TODO(antoniofilipovic) change to unknown
        ]
    )

    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_1))
    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_2))
    mg_sleep_and_assert_collection(leader_data, get_func_show_instances(coord_cursor_3))

    # 7

    interactive_mg_runner.start(inner_memgraph_instances, "instance_3")

    # 8

    leader_data = []
    leader_data.extend(coordinator_data)
    leader_data.extend(
        [
            ("instance_1", "", "127.0.0.1:10011", "down", "unknown"),
            ("instance_2", "", "127.0.0.1:10012", "up", "main"),
            ("instance_3", "", "127.0.0.1:10013", "up", "replica"),
        ]
    )

    follower_data = []
    follower_data.extend(coordinator_data)
    follower_data.extend(
        [
            ("instance_1", "", "", "unknown", "main"),  # TODO(antoniofilipovic) change to unknown
            ("instance_2", "", "", "unknown", "main"),
            ("instance_3", "", "", "unknown", "replica"),
        ]
    )

    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_1))
    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_2))
    mg_sleep_and_assert_collection(leader_data, get_func_show_instances(coord_cursor_3))

    # 9
    interactive_mg_runner.kill(inner_memgraph_instances, "instance_2")

    # 10
    leader_data = []
    leader_data.extend(coordinator_data)
    leader_data.extend(
        [
            ("instance_1", "", "127.0.0.1:10011", "down", "unknown"),
            ("instance_2", "", "127.0.0.1:10012", "down", "unknown"),
            ("instance_3", "", "127.0.0.1:10013", "up", "main"),
        ]
    )

    follower_data = []
    follower_data.extend(coordinator_data)
    follower_data.extend(
        [
            ("instance_1", "", "", "unknown", "main"),  # TODO(antoniofilipovic) change to unknown
            ("instance_2", "", "", "unknown", "main"),  # TODO(antoniofilipovic) change to unknown
            ("instance_3", "", "", "unknown", "main"),
        ]
    )

    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_1))
    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_2))
    mg_sleep_and_assert_collection(leader_data, get_func_show_instances(coord_cursor_3))

    # 11

    instance_3_cursor = connect(port=7689, host="localhost").cursor()

    with pytest.raises(Exception) as e:
        execute_and_fetch_all(instance_3_cursor, "CREATE ();")
    assert "At least one SYNC replica has not confirmed committing last transaction." in str(e.value)

    # 12
    interactive_mg_runner.start(inner_memgraph_instances, "instance_1")
    interactive_mg_runner.start(inner_memgraph_instances, "instance_2")

    # 13
    leader_data = []
    leader_data.extend(coordinator_data)
    leader_data.extend(
        [
            ("instance_1", "", "127.0.0.1:10011", "up", "replica"),
            ("instance_2", "", "127.0.0.1:10012", "up", "replica"),
            ("instance_3", "", "127.0.0.1:10013", "up", "main"),
        ]
    )

    follower_data = []
    follower_data.extend(coordinator_data)
    follower_data.extend(
        [
            ("instance_1", "", "", "unknown", "replica"),
            ("instance_2", "", "", "unknown", "replica"),
            ("instance_3", "", "", "unknown", "main"),
        ]
    )

    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_1))
    mg_sleep_and_assert_collection(follower_data, get_func_show_instances(coord_cursor_2))
    mg_sleep_and_assert_collection(leader_data, get_func_show_instances(coord_cursor_3))

    # 14.

    def show_replicas():
        return sorted(list(execute_and_fetch_all(instance_3_cursor, "SHOW REPLICAS;")))

    replicas = [
        (
            "instance_1",
            "127.0.0.1:10001",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 2, "behind": 0, "status": "ready"}},
        ),
        (
            "instance_2",
            "127.0.0.1:10002",
            "sync",
            {"ts": 0, "behind": None, "status": "ready"},
            {"memgraph": {"ts": 2, "behind": 0, "status": "ready"}},
        ),
    ]
    mg_sleep_and_assert_collection(replicas, show_replicas)

    def get_vertex_count_func(cursor):
        def get_vertex_count():
            return execute_and_fetch_all(cursor, "MATCH (n) RETURN count(n)")[0][0]

        return get_vertex_count

    mg_sleep_and_assert(1, get_vertex_count_func(connect(port=7687, host="localhost").cursor()))

    mg_sleep_and_assert(1, get_vertex_count_func(connect(port=7688, host="localhost").cursor()))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-rA"]))
