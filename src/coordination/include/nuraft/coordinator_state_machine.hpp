// Copyright 2024 Memgraph Ltd.
//
// Use of this software is governed by the Business Source License
// included in the file licenses/BSL.txt; by using this file, you agree to be bound by the terms of the Business Source
// License, and you may not use this file except in compliance with the Business Source License.
//
// As of the Change Date specified in that file, in accordance with
// the Business Source License, use of this software will be governed
// by the Apache License, Version 2.0, included in the file
// licenses/APL.txt.

#pragma once

#ifdef MG_ENTERPRISE

#include "coordination/coordinator_config.hpp"
#include "nuraft/coordinator_cluster_state.hpp"
#include "nuraft/raft_log_action.hpp"

#include <spdlog/spdlog.h>
#include <libnuraft/nuraft.hxx>

#include <variant>

namespace memgraph::coordination {

using nuraft::async_result;
using nuraft::buffer;
using nuraft::buffer_serializer;
using nuraft::cluster_config;
using nuraft::int32;
using nuraft::ptr;
using nuraft::snapshot;
using nuraft::state_machine;

class CoordinatorStateMachine : public state_machine {
 public:
  CoordinatorStateMachine() = default;
  CoordinatorStateMachine(CoordinatorStateMachine const &) = delete;
  CoordinatorStateMachine &operator=(CoordinatorStateMachine const &) = delete;
  CoordinatorStateMachine(CoordinatorStateMachine &&) = delete;
  CoordinatorStateMachine &operator=(CoordinatorStateMachine &&) = delete;
  ~CoordinatorStateMachine() override {}

  auto FindCurrentMainInstanceName() const -> std::optional<std::string>;
  auto MainExists() const -> bool;
  auto IsMain(std::string_view instance_name) const -> bool;
  auto IsReplica(std::string_view instance_name) const -> bool;

  static auto CreateLog(nlohmann::json &&log) -> ptr<buffer>;
  static auto SerializeRegisterInstance(CoordinatorClientConfig const &config) -> ptr<buffer>;
  static auto SerializeUnregisterInstance(std::string_view instance_name) -> ptr<buffer>;
  static auto SerializeSetInstanceAsMain(std::string_view instance_name) -> ptr<buffer>;
  static auto SerializeSetInstanceAsReplica(std::string_view instance_name) -> ptr<buffer>;
  static auto SerializeUpdateUUID(utils::UUID const &uuid) -> ptr<buffer>;

  static auto DecodeLog(buffer &data) -> std::pair<TRaftLog, RaftLogAction>;

  auto pre_commit(ulong log_idx, buffer &data) -> ptr<buffer> override;

  auto commit(ulong log_idx, buffer &data) -> ptr<buffer> override;

  auto commit_config(ulong log_idx, ptr<cluster_config> & /*new_conf*/) -> void override;

  auto rollback(ulong log_idx, buffer &data) -> void override;

  auto read_logical_snp_obj(snapshot & /*snapshot*/, void *& /*user_snp_ctx*/, ulong /*obj_id*/, ptr<buffer> &data_out,
                            bool &is_last_obj) -> int override;

  auto save_logical_snp_obj(snapshot &s, ulong &obj_id, buffer & /*data*/, bool /*is_first_obj*/, bool /*is_last_obj*/)
      -> void override;

  auto apply_snapshot(snapshot &s) -> bool override;

  auto free_user_snp_ctx(void *&user_snp_ctx) -> void override;

  auto last_snapshot() -> ptr<snapshot> override;

  auto last_commit_index() -> ulong override;

  auto create_snapshot(snapshot &s, async_result<bool>::handler_type &when_done) -> void override;

  auto GetInstances() const -> std::vector<InstanceState>;
  auto GetUUID() const -> utils::UUID;

 private:
  struct SnapshotCtx {
    SnapshotCtx(ptr<snapshot> &snapshot, CoordinatorClusterState const &cluster_state)
        : snapshot_(snapshot), cluster_state_(cluster_state) {}

    ptr<snapshot> snapshot_;
    CoordinatorClusterState cluster_state_;
  };

  auto create_snapshot_internal(ptr<snapshot> snapshot) -> void;

  CoordinatorClusterState cluster_state_;
  std::atomic<uint64_t> last_committed_idx_{0};

  std::map<uint64_t, ptr<SnapshotCtx>> snapshots_;
  std::mutex snapshots_lock_;

  ptr<snapshot> last_snapshot_;
  std::mutex last_snapshot_lock_;
};

}  // namespace memgraph::coordination
#endif
