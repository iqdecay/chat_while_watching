import struct


def headerBoxing(packet_type, sequence_number, info_length):
    """Sends back the header encoded in binary"""
    ## We shift the message type by 12 bits
    message_type = packet_type << 12
    pre_header = message_type + sequence_number
    packet_length = info_length+ 4
    packed_header = struct.pack("!hh", pre_header, packet_length)
    return packed_header




def headerUnboxing(packed_packet):
    """Decodes the header and sends it back"""
    unpacked_pre_header, packet_length = struct.unpack_from("!hh", packed_packet)
    packet_type = unpacked_pre_header >> 12
    sequence_number = unpacked_pre_header - (packet_type << 12)
    return packet_type, sequence_number, packet_length-4


def sendAcknowledgment(sequence_number, host_port, proxy):
    header = headerBoxing(0x0000, sequence_number, 0)
    proxy.transport.write(header, host_port)

