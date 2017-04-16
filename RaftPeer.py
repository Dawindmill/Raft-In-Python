import json
import socket
import logging
from queue import Queue
'''
Author: Bingfeng Liu
Date: 16/04/2017
'''

logger = logging.getLogger("RpcDriver")
FORMAT = '[%(asctime)-15s][%(levelname)s][%(host)s][%(port)s][%(funcName)s] %(message)s'
logging.basicConfig(format=FORMAT, level = logging.DEBUG)

#this RaftPeer is inspired from http://lesoluzioni.blogspot.com.au/2015/12/python-json-socket-serverclient.html
class RaftPeer:
    backlog = 5
    recv_buffer_size = 1024
    #thread safe queue FIFO
    #https://docs.python.org/2/library/queue.html

    def __init__(self, host, port):
        self.my_addr = {"host":str(host), "port":str(port)}
        logging.debug(" init raft peer " + str(host) + " " + str(port), extra = self.my_addr)
        #use to listen or recv message from other peers
        self.socket = socket.socket()
        #reuse the socket instead of waiting for OS to release the previous port
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.listen(self.backlog)
        #key is peer_addr => (ip, port)
        self.peers_addr_listen_socket = {}
        self.peers_addr_client_socket = {}
        self.json_message_queue = Queue()


    #[(ip, port)...]
    #def connect_to_all_peer(self, peer_ip_port_tuple_list):


    def connect_to_peer(self, peer_addr, peer_port):
        #use to send message to other peers
        client_socket = socket.socket()
        logging.debug("raft peer connect to " + str(peer_addr) + " " + str(peer_port), extra = self.my_addr)
        client_socket.connect((peer_addr, peer_port))
        self.peers_addr_client_socket[(peer_addr, peer_port)] = client_socket

    def accept(self):
        peer_socket, peer_addr = self.socket.accept()
        #peer_addr => (ip, port)
        self.peers_addr_listen_socket[peer_addr] = peer_socket
        logging.debug(" recv socket from " + str(peer_addr), extra = self.my_addr)

    def close(self):
        for peer_addr, socket_from_listen in self.peers_addr_listen_socket.items():
            socket_from_listen.close()
        for peer_addr, socket_from_client in self.peers_addr_client_socket.items():
            socket_from_client.close()
        self.socket.close()


    def _check_peer_in(self, peer_addr):
        if peer_addr not in self.peers_addr_listen_socket and peer_addr not in self.peers_addr_client_socket:
            logging.debug(" " + str(peer_addr) + " not in peers_addr_socket", extra = self.my_addr)
            return

    def sent_to_all_peer(self, json_data):
        logging.debug(" sending json_data to all peers as client ", extra = self.my_addr)
        for peer_addr in self.peers_addr_client_socket.keys():
            self.send_to_peer(peer_addr, json_data)

    def send_to_peer(self, peer_addr, json_data):
        logging.debug(" sending json_data to " + str(peer_addr), extra = self.my_addr)
        self._check_peer_in(peer_addr)
        peer_socket = self.peers_addr_client_socket[peer_addr]
        try:
            serialized_json_data = json.dumps(json_data)
            logging.debug(" json data serialization " + serialized_json_data, extra = self.my_addr)
            #send msg size
            #peer_socket.send(str.encode(str(len(serialized_json_data))+"\n", "utf-8"))
            logging.debug(" json data sent len " + str(len(serialized_json_data)), extra = self.my_addr)
            peer_socket.sendall(str.encode(serialized_json_data + "\n","utf-8"))
        except Exception as e:
            logging.debug(" json data serialization failed " + str(json_data) + str(e), extra = self.my_addr)
        #make it utf8r


    def receiv_from_all_peer(self):
        #this part is blocking for every client start a new thread ?
        #put them in a queue use one thread to do the job
        for peer_addr in self.peers_addr_listen_socket.keys():
            self.receive_from_one_peer_newline_delimiter(peer_addr)

    def receive_from_one_peer_newline_delimiter(self, peer_addr):
        logging.debug(" recv json_data from " + str(peer_addr), extra = self.my_addr)
        self._check_peer_in(peer_addr)
        peer_socket = self.peers_addr_listen_socket[peer_addr]
        msg = ""
        #could be wrong if msg size bigger than 1024, need further testing
        for i in range(1):
            msg += peer_socket.recv(1024).decode("utf-8")
            if "\n" in msg:
                msg_split_list = msg.split("\n")
                msg = msg_split_list[-1]
                for one_json_msg in msg_split_list[0:-1]:
                    try:
                        logging.debug(" recv one json_data " + one_json_msg, extra = self.my_addr)
                        one_deserialized_json_data = json.loads(one_json_msg)
                        self.json_message_queue.put(one_deserialized_json_data)
                        logging.debug(" put one json_data " + one_json_msg, extra = self.my_addr)
                    except Exception as e:
                        logging.debug( " deserialization recv json data failed " + str(e), extra = self.my_addr)
        logging.debug( " receive_from_one_peer_newline_delimiter terminated " + str(peer_addr), extra = self.my_addr)

    #this receiv need size first if want to use it change send_to_peer to send msg size first
    # def receive_from_peer(self, peer_addr):
    #     logging.debug(" recv json_data from " + str(peer_addr), extra = self.my_addr)
    #     self._check_peer_in(peer_addr)
    #     peer_socket = self.peers_addr_listen_socket[peer_addr]
    #     msg_length = ""
    #     one_byte = peer_socket.recv(1).decode("utf-8")
    #     logging.debug(" recv json_data receive json_data len " + one_byte, extra = self.my_addr)
    #
    #     while one_byte != '\n':
    #         logging.debug("loop recv json_data receive json_data len " + one_byte + " max_len => " + msg_length, extra = self.my_addr)
    #         msg_length += one_byte
    #         one_byte = peer_socket.recv(1).decode("utf-8")
    #
    #     logging.debug("finish recv json_data receive json_data len " + msg_length, extra = self.my_addr)
    #
    #     msg_length = int(msg_length)
    #     view = memoryview(bytearray(msg_length))
    #     next_offset = 0
    #     while msg_length - next_offset > 0:
    #         recv_size = peer_socket.recv_into(view[next_offset:], msg_length - next_offset)
    #         next_offset += recv_size
    #         logging.debug(" next_offset => " + str(next_offset), extra = self.my_addr)
    #         logging.debug(" recv_size => " + str(recv_size), extra = self.my_addr)
    #
    #
    #     try:
    #         logging.debug(" view => " + str(view.tobytes()), extra = self.my_addr)
    #         deserialized_json_data = json.loads(view.tobytes().decode("utf-8"))
    #         logging.debug(" recv json_data from " + str(peer_addr) + " json_data => " + str(deserialized_json_data), extra = self.my_addr)
    #         return deserialized_json_data
    #     except Exception as e:
    #         logging.debug( " deserialization recv json data failed " + str(e), extra = self.my_addr)
    #     logging.debug( "  recv json data failed retrun None", extra = self.my_addr)
    #     return None




