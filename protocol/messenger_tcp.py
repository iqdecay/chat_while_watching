# -*- coding: utf-8 -*-

import struct
from twisted.internet import reactor
from c2w.main.constants import ROOM_IDS as ROOM


def ip_from_string_to_tuple(address):
    """
    Take the address transform it in 4 int and return it
    :param address: string as a.b.c.d
    :return: 4 int : a, b, c, d
    """
    a, b, c, d = [int(i) for i in address.split('.')]
    return a, b, c, d


def ip_from_tuple_to_string(a, b, c, d):
    """
    Take the address under 4 int form and return it as string
    :param a, b, c, d: int
    :return: The address as string a.b.c.d
    """
    string_list = [str(i) for i in (a, b, c, d)]
    address = '.'.join(string_list)
    return address


# These packet types have info_length == 0
packet_types_without_info = [
    0b0000, 0b0011, 0b0100, 0b1000, 0b1001
]
empty_info = struct.pack("0s", "".encode("utf-8"))
empty_list = []


class Messenger:
    def __init__(self, proxy, transport, host_port):
        self.proxy = proxy
        self.transport = transport
        self.sending_queue = dict()
        self.sequence_numbers = {}
        self.receiving_functions = {}
        self.sending_functions = dict()
        self.sending_functions[0b0111] = self.send_chat_message
        self.base_counter = {"sent": 0,
                             "received": 0}
        self.base_sending_elt = {"sequence_number": 0,
                                 "datagram": "",
                                 "n_of_emission": 0,
                                 "host_port": 0,
                                 }
        self.ack_waiting_list = dict()
        self.current_callLater = dict()
        self.data_aggregate = b''
        self.transport_not_initialize = True

    def data_concatenate(self, data):
        aggregated_data = self.data_aggregate + data
        self.data_aggregate = aggregated_data
        if len(aggregated_data) >= 4:
            packet_type, sequence_number, info_length = self.header_unboxing(aggregated_data)
            if len(aggregated_data) >= (info_length + 4):
                self.receive_datagram(aggregated_data, self.host_port)
                self.data_aggregate = b''
            else:
                pass
        else:
            pass

    @staticmethod
    def header_boxing(packet_type, sequence_number, info_length):
        """Sends back the header encoded in binary"""
        # We shift the message type by 12 bits
        message_type = packet_type << 12
        pre_header = message_type + sequence_number
        packet_length = info_length + 4
        header_packed = struct.pack("!HH", pre_header, packet_length)
        return header_packed

    @staticmethod
    def header_unboxing(packed_packet):
        """Decodes the header and sends it back"""
        unpacked_pre_header, packet_length = struct.unpack_from("!HH", packed_packet)
        packet_type = unpacked_pre_header >> 12
        sequence_number = unpacked_pre_header & 0b11111111111
        info_length = packet_length - 4
        return packet_type, sequence_number, info_length

    def send_chat_message(self, username, chat_text, host_port):
        """
        Send chat_message to host_port
        :param username : of the person sending the chat_text
        :param chat_text: utf8-string
        :param host_port : of the recipient
        :return: nothing
        """
        # Pack the username
        username_encoded = username.encode("utf-8")
        username_length = len(username_encoded)
        fmt_string = "!{}s".format(username_length)
        username_packed = struct.pack(fmt_string, username_encoded)
        # Pack the username length
        username_length_packed = struct.pack("!B", username_length)
        # Pack the chat text
        chat_text_encoded = chat_text.encode("utf-8")
        fmt_string = "!{}s".format(len(chat_text_encoded))
        chat_text_packed = struct.pack(fmt_string, chat_text_encoded)
        # Pack the whole packet
        chat_message_packed = username_length_packed + username_packed + chat_text_packed
        self.send_info(0b0111, chat_message_packed, host_port)

    def pop_user(self, host_port):
        del self.sequence_numbers[host_port]
        del self.current_callLater[host_port]
        del self.sending_queue[host_port]

    def send_info(self, packet_type, packed_info, host_port):
        info_length = len(packed_info)
        if host_port not in self.sequence_numbers:
            self.add_client(host_port)
        sequence_number = self.sequence_numbers[host_port]["sent"]
        packed_header = self.header_boxing(packet_type, sequence_number, info_length)
        packet = packed_header + packed_info
        # Empty sending_queue ?
        if self.sending_queue[host_port] == empty_list:
            should_send = True
        else:
            should_send = False
        # Create the dict holding info about sent packet
        sending_elt = dict(self.base_sending_elt)
        sending_elt["datagram"] = packet
        sending_elt["host_port"] = host_port
        sending_elt["n_of_emission"] = 0
        sending_elt["sequence_number"] = sequence_number

        print("ADDING TO SENDING QUEUE : (seq number, datagram) ", sequence_number, packet)

        self.sending_queue[host_port].append(sending_elt)
        if should_send:
            self.send_next_message(host_port)
        # We increment the sequence number
        self.sequence_numbers[host_port]["sent"] += 1

    def send_acknowledgment(self, sequence_number, host_port):
        """
        Send acknowledgment for message to host_port
        :param sequence_number : of the acknowledged message
        :param host_port: sender of the acknowledged message
        :return: nothing
        """
        ack_header = self.header_boxing(0, sequence_number, 0)
        self.transmit_message(ack_header, host_port)

    def send_next_message(self, host_port):
        """
        Normally, send the next message in the sending queue. The message
        is sent over and over every second up to 7 times, upon which if no
        acknowledgment was received, the connection is severed.
        """
        current_datagram = self.sending_queue[host_port][0]["datagram"]
        current_host_port = self.sending_queue[host_port][0]["host_port"]
        current_n_of_emission = self.sending_queue[host_port][0]["n_of_emission"]
        current_seq_number = self.sending_queue[host_port][0]["sequence_number"]
        if current_n_of_emission >= 7:
            # --------------------------------MATHISSON EMERGENCY-------------------------------------
            if self.__class__.__name__ == "Server":
                self.pop_user(host_port)
                user = self.proxy.getUserByAddress(host_port)
                # sioux astuce :
                userChatRoom = user.userChatRoom
                self.proxy.removeUser(user.userName)
                self.update_user_list(userChatRoom, ROOM.OUT_OF_THE_SYSTEM_ROOM)

            if self.__class__.__name__ == "Client":
                self.quit_app()
        else:
            self.transmit_message(current_datagram, current_host_port)
            print("SENDING : (seq number, datagram, n° of emission) ", current_seq_number, current_datagram,
                  current_n_of_emission)
            self.sending_queue[host_port][0]["n_of_emission"] += 1
            self.current_callLater[host_port] = reactor.callLater(1, self.send_next_message, host_port)

    def transmit_message(self, datagram, host_port):
        # This function is called to send a message via the dedicated canal
        # The datagram is already packed and encoded
        if self.transport_not_initialize:
            self.transport = Protocol.transport
        self.transport.write(datagram)

    def receive_datagram(self, datagram, host_port):
        # Receive a datagram from host_port and treat it
        # For now we ignore ack from unknown hosts

        packet_type, sequence_number, info_length = self.header_unboxing(datagram)

        # If the packet is not an acknowledgment and not a login request
        if packet_type != 0b0000 and packet_type != 0b0001:
            # Ack is sent immediately, without going under the whole sending queue process
            self.send_acknowledgment(sequence_number, host_port)
            # If the host is known
            if host_port in self.sequence_numbers:
                if sequence_number == self.sequence_numbers[host_port]["received"]:
                    self.sequence_numbers[host_port]["received"] += 1
                    # Do the treatment_
                    self.receiving_functions[packet_type](datagram, info_length, host_port)
        # If the packet is a login request
        elif packet_type == 0b0001:
            # We immediately acknowledge it
            self.send_acknowledgment(sequence_number, host_port)
            # Then do the required treatment
            self.receiving_functions[packet_type](datagram, info_length, host_port)

        # If the packet is an ACK and there are packets waiting to be ACK
        elif packet_type == 0b0000 and host_port in self.sending_queue:
            if self.sending_queue[host_port] != empty_list:
                print("ACK RECEIVED n° : ", sequence_number)
                #  If the ACK corresponds to the one expected
                # ie if the ACK corresponds to a message not ACK yet
                if sequence_number == self.sending_queue[host_port][0]["sequence_number"]:
                    self.sending_queue[host_port].pop(0)
                    # Stop the packet emission
                    self.current_callLater[host_port].cancel()
                    # Transmit next packet if there is one
                    if host_port in self.sending_queue:
                        if self.sending_queue[host_port] != list():
                            print("CALLING NEXT MESSAGE THANKS TO ACK RECEIVED n° : ", sequence_number)
                            self.send_next_message(host_port)
                    if (host_port, sequence_number) in self.ack_waiting_list:
                        self.ack_waiting_list[(host_port, sequence_number)]()
        else:
            # We simply ignore the message
            pass

    @staticmethod
    def decipher_chat_message(buffer, info_length):
        """
        Decode a chat message and return the pseudo and content of the message
        :param buffer: the datagram containing the info
        :param info_length : integer
        :return: pseuodo, chat as utf-8 strings
        """
        len_parsed = 4
        # Unpack pseudo_length
        pseudo_length = struct.unpack_from("!B", buffer, len_parsed)[0]
        len_parsed += 1  # Because of type short
        # Unpack the pseudo
        fmt_string = "!{}s".format(pseudo_length)
        pseudo_encoded = struct.unpack_from(fmt_string, buffer, len_parsed)[0]
        pseudo = pseudo_encoded.decode("utf-8")
        len_parsed += pseudo_length
        # Unpack chat_text
        chat_length = info_length + 4 - len_parsed
        fmt_string = "!{}s".format(chat_length)
        chat_encoded = struct.unpack_from(fmt_string, buffer, len_parsed)[0]
        chat = chat_encoded.decode("utf-8")
        return pseudo, chat

    def add_client(self, host_port):
        self.sequence_numbers[host_port] = dict(self.base_counter)
        self.current_callLater[host_port] = None
        self.sending_queue[host_port] = []


class Server(Messenger):
    def __init__(self, proxy, transport, host_port):
        Messenger.__init__(self, proxy, transport, host_port)
        # We initialize server-specific sending functions
        # They all take (buffer, host_port) as argument, where buffer can be None
        self.host_port = host_port
        self.sending_functions[0b1000] = self.send_connection_accepted
        self.sending_functions[0b1001] = self.send_connection_refused
        self.sending_functions[0b0110] = self.send_user_list
        self.sending_functions[0b0101] = self.send_movie_list
        # We initialize server-specific sending functions
        # They all take (buffer, info_length, host_port) as argument where buffer can be empty
        self.receiving_functions[0b0100] = self.receive_quit_app
        self.receiving_functions[0b0011] = self.receive_quit_movie
        self.receiving_functions[0b0001] = self.receive_login_request
        self.receiving_functions[0b0010] = self.receive_movie_selection
        self.receiving_functions[0b0111] = self.distribute_chat

    def send_connection_accepted(self, null_info, host_port):
        self.send_info(0b1000, empty_info, host_port)

    def send_connection_refused(self, null_info, host_port):
        header = self.header_boxing(0b1001, 0, 0)
        packet = header + empty_info
        self.transmit_message(packet, host_port)

    def send_movie_list(self, movie_list, host_port):
        """ Pack the movie list and send it to host_port"""
        movie_list_packed = empty_info
        for movie_name, movie_ip_address, movie_port in movie_list:
            # Pack movie name
            movie_name_encoded = movie_name.encode("utf-8")
            fmt_string = "!{}s".format(len(movie_name_encoded))
            movie_name_packed = struct.pack(fmt_string, movie_name_encoded)
            # Pack length of movie name
            len_movie_name = len(movie_name_encoded)
            len_movie_name_packed = struct.pack("!B", len_movie_name)
            # Pack IP address as tuple of 4 int
            a, b, c, d = ip_from_string_to_tuple(movie_ip_address)
            address_packed = struct.pack("!BBBB", a, b, c, d)
            # Pack port number as long
            port_packed = struct.pack("!H", movie_port)
            # Pack the whole movie
            movie_element_packed = len_movie_name_packed + movie_name_packed + address_packed + port_packed
            # Add it to the list
            movie_list_packed += movie_element_packed
        self.send_info(0b0101, movie_list_packed, host_port)

    def send_user_list(self, user_list, host_port):
        """ Pack the user list and send it to host_port"""
        user_list_packed = empty_info
        for username, status in user_list:
            # Pack the username
            username_encoded = username.encode("utf-8")
            len_username = len(username_encoded)
            fmt_string = "!{}s".format(len_username)
            username_packed = struct.pack(fmt_string, username_encoded)
            # Pack status and len_username
            len_username_packed = struct.pack("!B", len_username)
            if status != ROOM.MAIN_ROOM:
                status = 1
            elif status == ROOM.MAIN_ROOM:
                status = 0
            status_packed = struct.pack("!B", status)
            # Pack the whole user
            user_element_packed = len_username_packed + username_packed + status_packed
            # Add it to the list
            user_list_packed += user_element_packed
        self.send_info(0b0110, user_list_packed, host_port)

    def receive_quit_app(self, buffer, info_length, host_port):
        user_instance = self.proxy.getUserByAddress(host_port)
        oldUserChatRoom = user_instance.userChatRoom
        # ----- POSSIBLE ISSUE----------
        # We remove the user from the system
        self.proxy.removeUser(user_instance.userName)
        self.pop_user(host_port)
        # We inform everyone impacted by this change
        self.update_user_list(oldUserChatRoom, ROOM.OUT_OF_THE_SYSTEM_ROOM)

    def receive_quit_movie(self, buffer, info_length, host_port):
        user_instance = self.proxy.getUserByAddress(host_port)
        oldUserChatRoom = user_instance.userChatRoom
        # We move the user to the main room
        self.proxy.updateUserChatroom(user_instance.userName, ROOM.MAIN_ROOM)
        # We inform everyone impacted by this change
        self.update_user_list(oldUserChatRoom, ROOM.MAIN_ROOM)

    def receive_login_request(self, buffer, info_length, host_port):
        """ Receive login request under packed buffer form from host_port"""
        offset = 4
        fmt_string = "!{}s".format(info_length)
        username_encoded = struct.unpack_from(fmt_string, buffer, offset)
        username = username_encoded[0].decode("utf-8")

        # We check if the username is already used
        if self.proxy.userExists(username):  # When it is : we reject the connection
            self.sending_functions[0b1001](empty_info, host_port)

        else:
            # Adding the user to the system
            newUser = self.proxy.addUser(username, ROOM.MAIN_ROOM, userAddress=host_port)
            self.add_client(host_port)
            # We increment the sequence number
            self.sequence_numbers[host_port]["received"] += 1

            # Accepting connection
            self.sending_functions[0b1000](empty_info, host_port)

            # Sending the user list to our new client as well as noticing eveyone in main room
            self.update_user_list(ROOM.OUT_OF_THE_SYSTEM_ROOM, ROOM.MAIN_ROOM)

            # Sending movie list
            movies = self.proxy.getMovieList()
            movie_list = []
            for movie in movies:
                movie_name = movie.movieTitle
                movie_ip_address = movie.movieIpAddress
                movie_port = movie.moviePort
                movie_list.append((movie_name, movie_ip_address, movie_port))
            self.sending_functions[0b0101](movie_list, host_port)

    def receive_movie_selection(self, buffer, info_length, host_port):
        """ Receive movie selection under packed buffer form from host_port"""
        offset = 4
        fmt_string = "!{}s".format(info_length)
        movie_name_encoded = struct.unpack_from(fmt_string, buffer, offset)[0]
        movie_name = movie_name_encoded.decode("utf-8")

        # We moove the user to the right movie room
        user = self.proxy.getUserByAddress(host_port)  # host-port ou adresse ? /_\ WARNING /_\
        # newUserChatRoom = self.proxy.getMovieByTitle(movie_name)
        self.proxy.updateUserChatroom(user.userName, movie_name)  # CHANGED HERE

        # We update the user list for everyone that needs to be aware of this change
        self.update_user_list(ROOM.MAIN_ROOM, movie_name)  # CHANGED HERE

        # We stream the movie
        self.proxy.startStreamingMovie(movie_name)

    def update_user_list(self, oldUserChatRoom, newUserChatRoom):
        # At least one of the rooms is the MAIN ROOM. The other is either OUT_OF_THE_SYSTEM_ROOM or a MOVIE ROOM.
        # Then we need to update the MOVIE ROOM if there is one.
        # If the user goes from a movie romm to main_room
        if oldUserChatRoom != ROOM.MAIN_ROOM and oldUserChatRoom != ROOM.OUT_OF_THE_SYSTEM_ROOM:
            self.update_movie_room(oldUserChatRoom)
        # If the user goes from from the mainroom to a movie room
        if newUserChatRoom != ROOM.MAIN_ROOM and newUserChatRoom != ROOM.OUT_OF_THE_SYSTEM_ROOM:
            self.update_movie_room(newUserChatRoom)
        # ------------------- WE NEED TO IMPLEMENT THE CASE WHEN THEY LEAVE THE SYSTEM
        # We update the MAIN ROOM first
        self.update_main_room()

    def update_main_room(self):
        users_in_system = self.proxy.getUserList()
        user_list = []
        users_in_main_room = []
        # Creating the list of all users with the right status
        for user in users_in_system:
            if user.userChatRoom == ROOM.MAIN_ROOM:
                user_list.append((user.userName, ROOM.MAIN_ROOM))
                users_in_main_room.append(user)
            else:
                user_list.append((user.userName, user.userChatRoom))
        # Now we need to send the information to everyone in MAIN ROOM
        for user in users_in_main_room:
            host_port = user.userAddress
            self.sending_functions[0b0110](user_list, host_port)
        print("users_in_system", users_in_system)
        print("user_list", user_list)
        print("users_in_main_room", users_in_main_room)

    def update_movie_room(self, chatRoom):
        users_in_system = self.proxy.getUserList()
        user_list = []
        users_in_movie_room = []
        # Creating the list of all users with the right status
        for user in users_in_system:
            if user.userChatRoom == chatRoom:
                user_list.append((user.userName, "M"))
                users_in_movie_room.append(user)
        # Now we need to send the information to everyone in the chatRoom
        for user in users_in_movie_room:
            host_port = user.userAddress
            self.sending_functions[0b0110](user_list, host_port)
        print("users_in_system", users_in_system)
        print("user_list", user_list)
        print("users_in_movie_room", users_in_movie_room)

    def distribute_chat(self, buffer, info_length, host_port):
        print("--------------------- WE RECEIVED A CHAT MESSAGE")
        # We first decode the message and the author of the chat message
        pseudo, chat = self.decipher_chat_message(buffer, info_length)
        # We then access the object user to locate him
        chat_author = self.proxy.getUserByName(pseudo)
        # We access the user list to find out who to send the message to
        users_in_system = self.proxy.getUserList()
        users_in_movie_room = list()
        # Creating the list of all users in the same room as the author
        for user in users_in_system:
            if user.userChatRoom == chat_author.userChatRoom and user != chat_author:
                users_in_movie_room.append(user)
        # Now we need to send the chat to everyone in the chatRoom
        for user in users_in_movie_room:
            self.send_chat_message(pseudo, chat, user.userAddress)


class Client(Messenger):
    def __init__(self, proxy, transport, host_port):
        Messenger.__init__(self, proxy, transport, host_port)
        self.host_port = host_port
        self.sequence_numbers = dict(self.base_counter)
        # We initialize client-specific sending functions
        # They all take (buffer, host_port) as argument, where buffer can be None
        self.sending_functions[0b0100] = self.send_quit_app
        self.sending_functions[0b1001] = self.send_quit_movie
        self.sending_functions[0b0001] = self.send_login_request
        self.sending_functions[0b0011] = self.send_movie_selection
        #  Receiving functions take (buffer, info_length, host_port) as arguments, where buffer is the packed datagram
        self.receiving_functions[0b0110] = self.decipher_user_list
        self.receiving_functions[0b0101] = self.decipher_movie_list
        self.receiving_functions[0b1000] = self.receive_connection_accepted
        self.receiving_functions[0b1001] = self.receive_connection_refused
        self.receiving_functions[0b0111] = self.receive_chat_message
        self.movieList = list()
        self.userList = list()
        self.movie = ROOM.MAIN_ROOM

    def send_login_request(self, pseudo_provided, host_port):
        """ Send login request with pseudo pseudo_provided to server at address host_port"""
        pseudo_encoded = pseudo_provided.encode("utf-8")
        fmt_string = "{}s".format(len(pseudo_encoded))
        pseudo_packed = struct.pack(fmt_string, pseudo_encoded)
        self.send_info(0b0001, pseudo_packed, host_port)

    def send_movie_selection(self, movie_title, host_port):
        """ Send movie selection with title movie_title to server at address host_port"""
        movie_title_encoded = movie_title.encode("utf-8")
        fmt_string = "{}s".format(len(movie_title_encoded))
        movie_title_packed = struct.pack(fmt_string, movie_title_encoded)
        sequence_number = self.sequence_numbers[host_port]["sent"]
        self.send_info(0b0010, movie_title_packed, host_port)
        # We need to memorize the seq number of this packet to isolate the ACK we will receive
        self.ack_waiting_list[(host_port, sequence_number)] = self.join_room_ok
        self.movie = movie_title

    def join_room_ok(self):
        self.proxy.joinRoomOKONE()

    def send_quit_movie(self, null_info, host_port):
        """ Send quitting movie decision to server at address host_port"""
        self.send_info(0b0011, empty_info, host_port)
        self.movie = ROOM.MAIN_ROOM
        sequence_number = self.sequence_numbers[host_port]["sent"]
        self.ack_waiting_list[(host_port, sequence_number)] = self.join_room_ok

    def send_quit_app(self, null_info, host_port):
        """ Send quitting app decision to server at address host_port"""
        self.send_info(0b0100, empty_info, host_port)
        sequence_number = self.sequence_numbers[host_port]["sent"]
        # We need to memorize the seq number of this packet to isolate the ACK we will receive
        self.ack_waiting_list[(host_port, sequence_number)] = self.quit_app()

    def decipher_user_list(self, buffer, info_length, host_port):
        """
        Decode user_list contained in buffer
        """
        user_list = []
        len_parsed = 4
        while len_parsed < info_length:
            pseudo_length = struct.unpack_from("!B", buffer, len_parsed)[0]
            len_parsed += 1  # It is a short
            pseudo_encoded = struct.unpack_from("!{}s".format(pseudo_length), buffer, len_parsed)[0]
            pseudo = pseudo_encoded.decode("utf_8")
            len_parsed += pseudo_length
            status_as_bit = struct.unpack_from("!B", buffer, len_parsed)[0]
            len_parsed += 1  # It is a short
            if status_as_bit == 1:
                if self.movie == ROOM.MAIN_ROOM:
                    status = "watching_movie"
                else:
                    status = self.movie
            elif status_as_bit == 0:
                status = ROOM.MAIN_ROOM
            else:
                raise ValueError("status isn't in the right format !!!")
            user_list.append((pseudo, status))
        self.userList = list(user_list)
        if self.movieList:  # Condition to determine if we are out of login process
            self.proxy.setUserListONE(self.userList)  # Updating userlist

    def decipher_movie_list(self, buffer, info_length, host_port):
        """Decode movie_list contained in buffer"""
        movie_list = []
        len_parsed = 4
        while len_parsed < info_length:
            # Unpack the title length
            title_length = struct.unpack_from("!B", buffer, len_parsed)[0]
            len_parsed += 1
            # Unpack
            fmt_string = "!{}s".format(title_length)
            title_encoded = struct.unpack_from(fmt_string, buffer, len_parsed)[0]
            title = title_encoded.decode("utf-8")
            len_parsed += title_length
            a, b, c, d = struct.unpack_from("!BBBB", buffer, len_parsed)
            address = ip_from_tuple_to_string(a, b, c, d)
            len_parsed += 4
            port = struct.unpack_from("!H", buffer, len_parsed)[0]
            len_parsed += 2
            movie_list.append((title, address, port))
        self.movieList = movie_list
        self.proxy.initCompleteONE(self.userList, self.movieList)

    def receive_connection_refused(self, buffer, info_length, host_port):
        self.proxy.connectionRejectedONE("Connection was refused by the server")
        self.proxy.applicationQuit()

    def receive_connection_accepted(self, buffer, info_length, host_port):
        print("Connection was accepted by server")

    def receive_chat_message(self, buffer, info_length, host_port):
        pseudo, chat = self.decipher_chat_message(buffer, info_length)
        self.proxy.chatMessageReceivedONE(pseudo, chat)

    def quit_app(self):
        self.proxy.leaveSystemOKONE()
        self.proxy.applicationQuit()
