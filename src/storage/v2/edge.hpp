#pragma once

#include <limits>
#include <unordered_map>

#include "utils/spin_lock.hpp"

#include "storage/v2/delta.hpp"
#include "storage/v2/gid.hpp"

namespace storage {

struct Vertex;

struct Edge {
  Edge(Gid gid, Delta *delta) : gid(gid), deleted(false), delta(delta) {
    CHECK(delta->action == Delta::Action::DELETE_OBJECT)
        << "Edge must be created with an initial DELETE_OBJECT delta!";
  }

  Gid gid;

  // TODO: add
  // std::unordered_map<uint64_t, storage::PropertyValue> properties;

  utils::SpinLock lock;
  bool deleted;
  // uint8_t PAD;
  // uint16_t PAD;

  Delta *delta;
};

inline bool operator==(const Edge &first, const Edge &second) {
  return first.gid == second.gid;
}
inline bool operator<(const Edge &first, const Edge &second) {
  return first.gid < second.gid;
}
inline bool operator==(const Edge &first, const Gid &second) {
  return first.gid == second;
}
inline bool operator<(const Edge &first, const Gid &second) {
  return first.gid < second;
}

}  // namespace storage
