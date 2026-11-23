"""Four deterministic Ethernet/IPv4/ICMP frames in a PCAP. No capture or packet transmission."""
import argparse
from pathlib import Path
import socket
import struct


def checksum(data):
    if len(data)%2:data+=b'\0'
    total=sum(struct.unpack('!'+str(len(data)//2)+'H',data))
    while total>>16:total=(total&65535)+(total>>16)
    return (~total)&65535


def make_pcap():
    result=bytearray(struct.pack('<IHHIIII',0xa1b2c3d4,2,4,0,0,65535,1))
    for number in range(4):
        payload=b'SMARTIR ITER12 SYNTHETIC OFFLINE PCAP ONLY '+str(number).encode()
        icmp=struct.pack('!BBHHH',8,0,0,12,number)+payload
        icmp=icmp[:2]+struct.pack('!H',checksum(icmp))+icmp[4:]
        ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(icmp),number+1,0,64,1,0,
                       socket.inet_aton('192.0.2.10'),socket.inet_aton('198.51.100.20'))
        ip=ip[:10]+struct.pack('!H',checksum(ip))+ip[12:]
        frame=bytes.fromhex('0200000000020200000000010800')+ip+icmp
        result.extend(struct.pack('<IIII',1767225600+number,123456,len(frame),len(frame)))
        result.extend(frame)
    return bytes(result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);args=parser.parse_args()
    with args.output.open('xb') as stream:stream.write(make_pcap())
