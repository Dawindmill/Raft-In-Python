import _thread
import json
import socket
import logging
from queue import Queue
from RaftPeerState import RaftPeerState
from LogData import LogData

'''
Author: Bingfeng Liu
Date: 16/04/2017
'''
FORMAT = '[%(module)s][%(asctime)-15s][%(levelname)s][%(peer_id)s][%(host)s][%(port)s][%(funcName)s] %(message)s'
logging.basicConfig(format=FORMAT, level = logging.DEBUG)
logger = logging.getLogger("RpcDriver")


#this RaftPeer is inspired from http://lesoluzioni.blogspot.com.au/2015/12/python-json-socket-serverclient.html
class RaftPeer:
    backlog = 5
    recv_buffer_size = 1024
    #thread safe queue FIFO
    #https://docs.python.org/2/library/queue.html

    def __init__(self, host, port, peer_id):
        self.my_addr_port_tuple = (host, port)
        self.peer_id = peer_id
        self.my_detail = {"host":str(host), "port":str(port), "peer_id":str(peer_id)}
        logger.debug(" init raft peer " + str(host) + " " + str(port), extra = self.my_detail)
        #use to listen or recv message from other peers
        self.socket = socket.socket()
        #reuse the socket instead of waiting for OS to release the previous port
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.listen(self.backlog)
        #key is peer_addr => (ip, port)
        #used to rec message
        self.peers_addr_listen_socket = {}
        #used to send message
        self.peers_addr_client_socket = {}
        #when recv fron server listen port, we must include sender's listen port and ip
        #other wise we dont know the msg is from which peer and send to who in peer_addr_client_socket
        #in peer_addr_client_socket we use known peer's ip and port as key
        self.json_message_recv_queue = Queue()
        self.json_message_send_queue = Queue()
        self.raft_peer_state = RaftPeerState(self.my_addr_port_tuple, self.peer_id)
        try:
            #use argument (first_arg, second_arg, ) note the extra last comma might be needed?
            _thread.start_new_thread(self.process_json_message_send_queue, ())
            logger.debug( " start thread => process_json_message_send_queue successful ", extra = self.my_detail )
            _thread.start_new_thread(self.process_json_message_recv_queue, ())
            logger.debug( " start thread => process_json_message_recv_queue successful ", extra = self.my_detail )
            _thread.start_new_thread(self.accept, ())
            logger.debug( " start thread => accept successful ", extra = self.my_detail )

        except Exception as e:
            logger.debug( "Error: unable to start processing threads " + str(e), extra = self.my_detail )


    def process_json_message_recv_queue(self):
        while True:
            one_recv_json_message = self.json_message_recv_queue.get()
            logger.debug( " processing one recv message " + str(one_recv_json_message), extra = self.my_detail )
            #in json encode it is two element list
            senpeer_addr, peer_port = one_recv_json_message["send_from"]
            one_recv_json_message_type = one_recv_json_message["msg_type"]


    def process_json_message_send_queue(self):
        while True:
            one_send_json_message = self.json_message_send_queue.get()
            logger.debug( " processing one send message " + str(one_send_json_message), extra = self.my_detail )
            #in json encode it is two element list
            peer_addr, peer_port = one_send_json_message["send_to"]
            self.send_to_peer((peer_addr, peer_port), one_send_json_message)


    #[(ip => str, port => int)...]
    def connect_to_all_peer(self, peer_addr_port_tuple_list):
        my_peer_addr_port_tuple = (self.my_detail['host'], int(self.my_detail['port']))
        #in referece remove
        peer_addr_port_tuple_list.remove(my_peer_addr_port_tuple)
        for one_peer_addr, one_peer_port in peer_addr_port_tuple_list:
            self.connect_to_peer((one_peer_addr, one_peer_port))


    def connect_to_peer(self, peer_addr_port_tuple):
        #use to send message to other peers
        client_socket = socket.socket()
        logger.debug("raft peer connect to " + str(peer_addr_port_tuple), extra = self.my_detail)
        client_socket.connect(peer_addr_port_tuple)
        self.peers_addr_client_socket[peer_addr_port_tuple] = client_socket

    def accept(self):
        while True:
            peer_socket, peer_addr_port_tuple = self.socket.accept()
            #peer_addr => (ip, port)
            self.peers_addr_listen_socket[peer_addr_port_tuple] = peer_socket
            logger.debug(" recv socket from " + str(peer_addr_port_tuple), extra = self.my_detail)
            try:
                _thread.start_new_thread(self.receive_from_one_peer_newline_delimiter, (peer_addr_port_tuple, ))
                logger.debug(" creating recv thread successful => " + str(peer_addr_port_tuple), extra = self.my_detail)
            except Exception as e:
                logger.debug(" creating recv thread failed => " + str(peer_addr_port_tuple), extra = self.my_detail)

    def close(self):
        for peer_addr, socket_from_listen in self.peers_addr_listen_socket.items():
            socket_from_listen.close()
        for peer_addr, socket_from_client in self.peers_addr_client_socket.items():
            socket_from_client.close()
        self.socket.close()


    def _check_peer_in(self, peer_addr):
        if peer_addr not in self.peers_addr_listen_socket and peer_addr not in self.peers_addr_client_socket:
            logger.debug(" " + str(peer_addr) + " not in peers_addr_socket", extra = self.my_detail)
            return

    def sent_to_all_peer(self, json_data_dict):
        logger.debug(" sending json_data to all peers as client ", extra = self.my_detail)
        for peer_addr in self.peers_addr_client_socket.keys():
            self.send_to_peer(peer_addr, json_data_dict)

    def send_to_peer(self, peer_addr_port_tuple, json_data_dict):
        logger.debug(" sending json_data to " + str(peer_addr_port_tuple), extra = self.my_detail)
        self._check_peer_in(peer_addr_port_tuple)
        peer_socket = self.peers_addr_client_socket[peer_addr_port_tuple]
        try:
            serialized_json_data = json.dumps(json_data_dict)
            logger.debug(" json data serialization " + serialized_json_data, extra = self.my_detail)
            #send msg size
            #peer_socket.send(str.encode(str(len(serialized_json_data))+"\n", "utf-8"))
            logger.debug(" json data sent len " + str(len(serialized_json_data)), extra = self.my_detail)
            peer_socket.sendall(str.encode(serialized_json_data + "\n","utf-8"))
        except Exception as e:
            logger.debug(" json data serialization failed " + str(json_data_dict) + str(e), extra = self.my_detail)
        #make it utf8r


    def receiv_from_all_peer(self):
        #this part is blocking for every client start a new thread ?
        #put them in a queue use one thread to do the job
        for peer_addr in self.peers_addr_listen_socket.keys():
            self.receive_from_one_peer_newline_delimiter(peer_addr)

    def receive_from_one_peer_newline_delimiter(self, peer_addr_port_tuple):
        logger.debug(" recv json_data from " + str(peer_addr_port_tuple), extra = self.my_detail)
        self._check_peer_in(peer_addr_port_tuple)
        peer_socket = self.peers_addr_listen_socket[peer_addr_port_tuple]
        msg = ""
        #could be wrong if msg size bigger than 1024, need further testing
        for i in range(1):
            msg += peer_socket.recv(1024).decode("utf-8")
            if "\n" in msg:
                msg_split_list = msg.split("\n")
                msg = msg_split_list[-1]
                for one_json_msg in msg_split_list[0:-1]:
                    try:
                        logger.debug(" recv one json_data " + one_json_msg, extra = self.my_detail)
                        one_deserialized_json_data = json.loads(one_json_msg)
                        self.json_message_recv_queue.put(one_deserialized_json_data)
                        logger.debug(" put one json_data " + one_json_msg, extra = self.my_detail)
                    except Exception as e:
                        logger.debug( " deserialization recv json data failed " + str(e), extra = self.my_detail)
        logger.debug( " receive_from_one_peer_newline_delimiter terminated " + str(peer_addr_port_tuple), extra = self.my_detail)

    #this receiv need size first if want to use it change send_to_peer to send msg size first
    # def receive_from_peer(self, peer_addr):
    #     logger.debug(" recv json_data from " + str(peer_addr), extra = self.my_detail)
    #     self._check_peer_in(peer_addr)
    #     peer_socket = self.peers_addr_listen_socket[peer_addr]
    #     msg_length = ""
    #     one_byte = peer_socket.recv(1).decode("utf-8")
    #     logger.debug(" recv json_data receive json_data len " + one_byte, extra = self.my_detail)
    #
    #     while one_byte != '\n':
    #         logger.debug("loop recv json_data receive json_data len " + one_byte + " max_len => " + msg_length, extra = self.my_detail)
    #         msg_length += one_byte
    #         one_byte = peer_socket.recv(1).decode("utf-8")
    #
    #     logger.debug("finish recv json_data receive json_data len " + msg_length, extra = self.my_detail)
    #
    #     msg_length = int(msg_length)
    #     view = memoryview(bytearray(msg_length))
    #     next_offset = 0
    #     while msg_length - next_offset > 0:
    #         recv_size = peer_socket.recv_into(view[next_offset:], msg_length - next_offset)
    #         next_offset += recv_size
    #         logger.debug(" next_offset => " + str(next_offset), extra = self.my_detail)
    #         logger.debug(" recv_size => " + str(recv_size), extra = self.my_detail)
    #
    #
    #     try:
    #         logger.debug(" view => " + str(view.tobytes()), extra = self.my_detail)
    #         deserialized_json_data = json.loads(view.tobytes().decode("utf-8"))
    #         logger.debug(" recv json_data from " + str(peer_addr) + " json_data => " + str(deserialized_json_data), extra = self.my_detail)
    #         return deserialized_json_data
    #     except Exception as e:
    #         logger.debug( " deserialization recv json data failed " + str(e), extra = self.my_detail)
    #     logger.debug( "  recv json data failed retrun None", extra = self.my_detail)
    #     return None




