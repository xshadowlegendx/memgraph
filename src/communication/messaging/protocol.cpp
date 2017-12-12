#include <sstream>

#include "communication/messaging/distributed.hpp"
#include "communication/messaging/local.hpp"
#include "communication/messaging/protocol.hpp"

#include "fmt/format.h"
#include "glog/logging.h"

namespace communication::messaging {

Session::Session(Socket &&socket, SessionData &data)
    : socket_(std::move(socket)), system_(data.system) {}

bool Session::Alive() const { return alive_; }

std::string Session::GetStringAndShift(SizeT len) {
  std::string ret(reinterpret_cast<char *>(buffer_.data()), len);
  buffer_.Shift(len);
  return ret;
}

void Session::Execute() {
  if (buffer_.size() < sizeof(SizeT)) return;
  SizeT len_channel = GetLength();
  if (buffer_.size() < 2 * sizeof(SizeT) + len_channel) return;
  SizeT len_data = GetLength(sizeof(SizeT) + len_channel);
  if (buffer_.size() < 2 * sizeof(SizeT) + len_data + len_channel) return;

  // Remove the length bytes from the buffer.
  buffer_.Shift(sizeof(SizeT));
  auto channel = GetStringAndShift(len_channel);
  buffer_.Shift(sizeof(SizeT));

  // TODO: check for exceptions
  std::istringstream stream;
  stream.str(std::string(reinterpret_cast<char *>(buffer_.data()), len_data));
  ::cereal::BinaryInputArchive iarchive{stream};
  std::unique_ptr<Message> message{nullptr};
  iarchive(message);
  buffer_.Shift(len_data);

  LocalWriter writer(system_, channel);
  writer.Send(std::move(message));
}

StreamBuffer Session::Allocate() { return buffer_.Allocate(); }

void Session::Written(size_t len) { buffer_.Written(len); }

void Session::Close() {
  DLOG(INFO) << "Closing session";
  this->socket_.Close();
}

SizeT Session::GetLength(int offset) {
  SizeT ret = *reinterpret_cast<SizeT *>(buffer_.data() + offset);
  return ret;
}

bool SendLength(Socket &socket, SizeT length) {
  return socket.Write(reinterpret_cast<uint8_t *>(&length), sizeof(SizeT));
}

void SendMessage(const std::string &address, uint16_t port,
                 const std::string &channel, std::unique_ptr<Message> message) {
  CHECK(message) << "Trying to send nullptr instead of message";

  // Initialize endpoint.
  Endpoint endpoint(address.c_str(), port);

  Socket socket;
  if (!socket.Connect(endpoint)) {
    LOG(INFO) << "Couldn't connect to remote address: " << address << ":"
              << port;
    return;
  }

  if (!SendLength(socket, channel.size())) {
    LOG(INFO) << "Couldn't send channel size!";
    return;
  }
  if (!socket.Write(channel)) {
    LOG(INFO) << "Couldn't send channel data!";
    return;
  }

  // Serialize and send message
  std::ostringstream stream;
  ::cereal::BinaryOutputArchive oarchive(stream);
  oarchive(message);

  const std::string &buffer = stream.str();
  int64_t message_size = 2 * sizeof(SizeT) + buffer.size() + channel.size();
  CHECK(message_size <= kMaxMessageSize) << fmt::format(
      "Trying to send message of size {}, max message size is {}", message_size,
      kMaxMessageSize);

  if (!SendLength(socket, buffer.size())) {
    LOG(INFO) << "Couldn't send message size!";
    return;
  }
  if (!socket.Write(buffer)) {
    LOG(INFO) << "Couldn't send message data!";
    return;
  }
}
}
