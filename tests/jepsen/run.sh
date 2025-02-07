#!/bin/bash
set -Eeuo pipefail
script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

MEMGRAPH_BINARY_PATH="../../build/memgraph"
# NOTE: Jepsen Git tags are not consistent, there are: 0.2.4, v0.3.0, 0.3.2, ...
# NOTE: On Ubuntu 22.04 v0.3.2 uses non-existing docker compose --compatibility flag.
# NOTE: On Ubuntu 22.04 v0.3.0 and v0.3.1 seems to be runnable.
# TODO(gitbuda): Make sure Memgraph can be testes with Jepsen >= 0.3.0
JEPSEN_VERSION="${JEPSEN_VERSION:-0.2.4}"
JEPSEN_ACTIVE_NODES_NO=5
CONTROL_LEIN_RUN_ARGS="test-all --node-configs resources/node-config.edn"
CONTROL_LEIN_RUN_STDOUT_LOGS=1
CONTROL_LEIN_RUN_STDERR_LOGS=1
_JEPSEN_RUN_EXIT_STATUS=0
PRINT_CONTEXT() {
    echo -e "MEMGRAPH_BINARY_PATH:\t\t $MEMGRAPH_BINARY_PATH"
    echo -e "JEPSEN_VERSION:\t\t\t $JEPSEN_VERSION"
    echo -e "JEPSEN_ACTIVE_NODES_NO:\t\t $JEPSEN_ACTIVE_NODES_NO"
    echo -e "CONTROL_LEIN_RUN_ARGS:\t\t $CONTROL_LEIN_RUN_ARGS"
    echo -e "CONTROL_LEIN_RUN_STDOUT_LOGS:\t $CONTROL_LEIN_RUN_STDOUT_LOGS"
    echo -e "CONTROL_LEIN_RUN_STDERR_LOGS:\t $CONTROL_LEIN_RUN_STDERR_LOGS"
}

HELP_EXIT() {
    echo ""
    echo "HELP: $0 help|cluster-up|cluster-refresh|cluster-cleanup|cluster-dealloc|mgbuild|test|test-all-individually [args]"
    echo ""
    echo "    test args --binary                 MEMGRAPH_BINARY_PATH"
    echo "              --ignore-run-stdout-logs Ignore lein run stdout logs."
    echo "              --ignore-run-stderr-logs Ignore lein run stderr logs."
    echo "              --nodes-no               JEPSEN_ACTIVE_NODES_NO"
    echo "              --run-args               \"CONTROL_LEIN_RUN_ARGS\" (NOTE: quotes)"
    echo ""
    exit 1
}

ERROR() {
    /bin/echo -e "\e[101m\e[97m[ERROR]\e[49m\e[39m" "$@"
}

INFO() {
    /bin/echo -e "\e[104m\e[97m[INFO]\e[49m\e[39m" "$@"
}

if ! command -v docker > /dev/null 2>&1 || ! command -v docker-compose > /dev/null 2>&1; then
  ERROR "docker and docker-compose have to be installed."
  exit 1
fi

if [ ! -d "$script_dir/jepsen" ]; then
    git clone https://github.com/jepsen-io/jepsen.git -b "$JEPSEN_VERSION" "$script_dir/jepsen"
    if [ "$JEPSEN_VERSION" == "v0.3.0" ]; then
        if [ -f "$script_dir/jepsen_0.3.0.patch" ]; then
            cd "$script_dir/jepsen"
            git apply "$script_dir/jepsen_0.3.0.patch"
            cd "$script_dir"
        fi
    fi
fi

if [ "$#" -lt 1 ]; then
    HELP_EXIT
fi

PROCESS_ARGS() {
    shift
    while [[ $# -gt 0 ]]; do
        key="$1"
        case $key in
            --binary)
                shift
                MEMGRAPH_BINARY_PATH="$1"
                shift
            ;;
            --ignore-run-stdout-logs)
                CONTROL_LEIN_RUN_STDOUT_LOGS=0
                shift
            ;;
            --ignore-run-stderr-logs)
                CONTROL_LEIN_RUN_STDERR_LOGS=0
                shift
            ;;
            --nodes-no)
                shift
                JEPSEN_ACTIVE_NODES_NO="$1"
                shift
            ;;
            --run-args)
                shift
                CONTROL_LEIN_RUN_ARGS="$1"
                shift
            ;;
            *)
                ERROR "Unknown option $1."
                HELP_EXIT
            ;;
        esac
    done
}

COPY_BINARIES() {
   # Copy Memgraph binary, handles both cases, when binary is a sym link
   # or a regular file.
   binary_path="$MEMGRAPH_BINARY_PATH"
   if [ -L "$binary_path" ]; then
       binary_path=$(readlink "$binary_path")
   fi
   binary_name=$(basename -- "$binary_path")
   for iter in $(seq 1 "$JEPSEN_ACTIVE_NODES_NO"); do
       jepsen_node_name="jepsen-n$iter"
       docker_exec="docker exec $jepsen_node_name bash -c"
       if [ "$binary_name" == "memgraph" ]; then
         _binary_name="memgraph_tmp"
       else
         _binary_name="$binary_name"
       fi
       $docker_exec "rm -rf /opt/memgraph/ && mkdir -p /opt/memgraph"
       docker cp "$binary_path" "$jepsen_node_name":/opt/memgraph/"$_binary_name"
       $docker_exec "ln -s /opt/memgraph/$_binary_name /opt/memgraph/memgraph"
       $docker_exec "touch /opt/memgraph/memgraph.log"
       INFO "Copying $binary_name to $jepsen_node_name DONE."
   done
   # Copy test files into the control node.
   docker exec jepsen-control mkdir -p /jepsen/memgraph/store
   docker cp "$script_dir/src/." jepsen-control:/jepsen/memgraph/src/
   docker cp "$script_dir/test/." jepsen-control:/jepsen/memgraph/test/
   docker cp "$script_dir/resources/." jepsen-control:/jepsen/memgraph/resources/
   docker cp "$script_dir/project.clj" jepsen-control:/jepsen/memgraph/project.clj
   INFO "Copying test files to jepsen-control DONE."
}

RUN_JEPSEN() {
    __control_lein_run_args="$1"
    # NOTE: docker exec -t is NOT ok because gh CI user does NOT have TTY.
    # NOTE: ~/.bashrc has to be manually sourced when bash -c is used
    #       because some Jepsen config is there.
    # To be able to archive the run result even if the run fails.
    set +e
    if [ "$CONTROL_LEIN_RUN_STDOUT_LOGS" -eq 0 ]; then
        redirect_stdout_logs="/dev/null"
    else
        redirect_stdout_logs="/dev/stdout"
    fi
    if [ "$CONTROL_LEIN_RUN_STDERR_LOGS" -eq 0 ]; then
        redirect_stderr_logs="/dev/null"
    else
        redirect_stderr_logs="/dev/stderr"
    fi
    docker exec jepsen-control bash -c "source ~/.bashrc && cd memgraph && lein run $__control_lein_run_args" 1> $redirect_stdout_logs 2> $redirect_stderr_logs
    _JEPSEN_RUN_EXIT_STATUS=$?
    set -e
}

PROCESS_RESULTS() {
    start_time="$1"
    end_time="$2"
    INFO "Process results..."
    echo "Start time: ${start_time}, End time: ${end_time}"
    # Print and pack all test workload runs between start and end time.
    all_workloads=$(docker exec jepsen-control bash -c 'ls /jepsen/memgraph/store/' | grep test-)
    all_workload_run_folders=""
    for workload in $all_workloads; do
        for time_folder in $(docker exec jepsen-control bash -c "ls /jepsen/memgraph/store/$workload"); do
            if [[ "$time_folder" == "latest" ]]; then
                continue
            fi
            # The early continue pattern here is nice because bash doesn't
            # have >= for the string comparison (marginal values).
            if [[ "$time_folder" < "$start_time" ]]; then
                continue
            fi
            if [[ "$time_folder" > "$end_time" ]]; then
                continue
            fi
            INFO "jepsen.log for $workload/$time_folder"
            docker exec jepsen-control bash -c "tail -n 50 /jepsen/memgraph/store/$workload/$time_folder/jepsen.log"
            all_workload_run_folders="$all_workload_run_folders /jepsen/memgraph/store/$workload/$time_folder"
        done
    done
    INFO "Packing results..."
    docker exec jepsen-control bash -c "tar -czvf /jepsen/memgraph/Jepsen.tar.gz $all_workload_run_folders"
    docker cp jepsen-control:/jepsen/memgraph/Jepsen.tar.gz ./
    INFO "Result processing (printing and packing) DONE."
}

CLUSTER_UP() {
  PRINT_CONTEXT
  "$script_dir/jepsen/docker/bin/up" --daemon
  sleep 10
  # Ensure all SSH connections between Jepsen containers work
  for node in $(docker ps --filter name=jepsen* --filter status=running --format "{{.Names}}"); do
      if [ "$node" == "jepsen-control" ]; then
          continue
      fi
      node_hostname="${node##jepsen-}"
      docker exec jepsen-control bash -c "ssh -oStrictHostKeyChecking=no -t $node_hostname exit"
  done
}

CLUSTER_DEALLOC() {
  ps=$(docker ps --filter name=jepsen* --filter status=running -q)
  if [[ ! -z ${ps} ]]; then
      echo "Killing ${ps}"
      docker rm -f ${ps}
      imgs=$(docker images "jepsen*" -q)
      if [[ ! -z ${imgs} ]]; then
          echo "Removing ${imgs}"
          docker images "jepsen*" -q | xargs docker image rmi -f
      else
          echo "No Jepsen images detected!"
      fi
  else
      echo "No Jepsen containers detected!"
  fi
}

# Initialize testing context by copying source/binary files. Inside CI,
# Memgraph is tested on a single machine cluster based on Docker containers.
# Once these tests will be part of the official Jepsen repo, the majority of
# functionalities inside this script won't be needed because each node clones
# the public repo.
case $1 in
    # Start Jepsen Docker cluster of 5 nodes. To configure the cluster please
    # take a look under jepsen/docker/docker-compose.yml.
    # NOTE: If you delete the jepsen folder where docker config is located,
    # the current cluster is broken because it relies on the folder. That can
    # happen easiliy because the jepsen folder is git ignored.
    cluster-up)
        CLUSTER_UP
    ;;

    cluster-refresh)
        CLUSTER_DEALLOC
        CLUSTER_UP
    ;;

    cluster-dealloc)
        CLUSTER_DEALLOC
    ;;

    cluster-cleanup)
        jepsen_control_exec="docker exec jepsen-control bash -c"
        INFO "Deleting /jepsen/memgraph/store/* on jepsen-control"
        $jepsen_control_exec "rm -rf /jepsen/memgraph/store/*"
        for iter in $(seq 1 "$JEPSEN_ACTIVE_NODES_NO"); do
            jepsen_node_name="jepsen-n$iter"
            jepsen_node_exec="docker exec $jepsen_node_name bash -c"
            INFO "Deleting /opt/memgraph/* on $jepsen_node_name"
            $jepsen_node_exec "rm -rf /opt/memgraph/*"
        done
    ;;

    mgbuild)
        PRINT_CONTEXT
        echo ""
        echo "TODO(gitbuda): Build memgraph for Debian 10 via memgraph/memgraph-builder"
        exit 1
    ;;

    test)
        PROCESS_ARGS "$@"
        PRINT_CONTEXT
        COPY_BINARIES
        start_time="$(docker exec jepsen-control bash -c 'date -u +"%Y%m%dT%H%M%S"').000Z"
        INFO "Jepsen run in progress... START_TIME: $start_time"
        RUN_JEPSEN "$CONTROL_LEIN_RUN_ARGS"
        end_time="$(docker exec jepsen-control bash -c 'date -u +"%Y%m%dT%H%M%S"').000Z"
        INFO "Jepsen run DONE. END_TIME: $end_time"
        PROCESS_RESULTS "$start_time" "$end_time"
        # Exit if the jepsen run status is not 0
        if [ "$_JEPSEN_RUN_EXIT_STATUS" -ne 0 ]; then
            ERROR "Jepsen FAILED" # important for the coder
            exit "$_JEPSEN_RUN_EXIT_STATUS" # important for CI
        fi
    ;;

    test-all-individually)
        PROCESS_ARGS "$@"
        PRINT_CONTEXT
        INFO "NOTE: CONTROL_LEIN_RUN_ARGS ignored"
        COPY_BINARIES
        start_time="$(docker exec jepsen-control bash -c 'date -u +"%Y%m%dT%H%M%S"').000Z"
        INFO "Jepsen run in progress... START_TIME: $start_time"
        for workload in "bank" "large"; do
          RUN_JEPSEN "test --workload $workload --node-configs resources/node-config.edn"
          if [ "$_JEPSEN_RUN_EXIT_STATUS" -ne 0 ]; then
            break
          fi
        done
        end_time="$(docker exec jepsen-control bash -c 'date -u +"%Y%m%dT%H%M%S"').000Z"
        INFO "Jepsen run DONE. END_TIME: $end_time"
        PROCESS_RESULTS "$start_time" "$end_time"
        # Exit if the jepsen run status is not 0
        if [ "$_JEPSEN_RUN_EXIT_STATUS" -ne 0 ]; then
            ERROR "Jepsen FAILED" # important for the coder
            exit "$_JEPSEN_RUN_EXIT_STATUS" # important for CI
        fi
    ;;

    *)
        HELP_EXIT
    ;;
esac
