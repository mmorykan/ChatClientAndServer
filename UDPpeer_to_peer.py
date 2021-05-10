import asyncio
import socket
import struct
import time
"""
This program runs a chat client using the UDP Peer to Peer Protocol.
"""

PORT = 65432

def get_ip():
    """Gets the local IP of the current machine."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(('10.255.255.255', 1)) # random IP address, doesn't have to be reachable
            return s.getsockname()[0] # get the outgoing IP address on the machine
        except:
            return '127.0.0.1'


class ChatProtocol(asyncio.DatagramProtocol):
    def __init__(self):
        self.on_con_lost = asyncio.get_running_loop().create_future()
        self.messages = []
        self.username = ''


    def connection_made(self, transport):
        """Method called when the connection is initially made."""
        self.transport = transport

        # Starts getting messages as a task in the asyncio loop
        asyncio.create_task(self.send_messages())


    async def send_messages(self):
        """
        Prompts the peer for input for usernme and messages.
        Broadcasts the username and messages
        """
        loop = asyncio.get_running_loop()

        username = await loop.run_in_executor(None, lambda: input('Enter a username: '))

        if not username:
            self.transport.close()
            return

        self.username = username
        self.transport.sendto(('1' + username).encode(), ('255.255.255.255', PORT))

        while True:
            message = await loop.run_in_executor(None, input)

            if not message:
                self.transport.close()
                break

            self.transport.sendto(('2' + str(time.strftime('%X')) + ' ' + self.username + ' ' + message).encode(), ('255.255.255.255', PORT))


    def connection_lost(self, exc):
        """Method called whenever the transport is closed."""
        self.on_con_lost.set_result(True)


    def datagram_received(self, data, addr):
        """
        Method called whenever a datagram is recieved.
        Validates username
        Sends up to the ten most recent messages
        """
        data = data.decode()
        if addr[0] != get_ip():            
            if data[0] == '1':
                username = data[1:]

                if username == self.username:
                    self.transport.sendto(('False').encode(), addr)
                else:
                    for message in self.messages[-10:]:
                        self.transport.sendto(('2' + message).encode(), addr)

            if data == 'False': 
                self.transport.close()

        if data[0] == '2' and data[1:] not in self.messages:
            self.messages.append(data[1:])
            print(self.messages[-1])


    def error_received(self, exc):
        """Method called whenever there is an error with the underlying communication."""
        print('Error received:', exc)


async def main():
    """
    This main function sets up the broadcast socket and binds the socket to the predefined port
    Creates the transport for every peer
    """
    # Setup the socket we will be using - enable broadcast and recieve message on the given port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, True)
    sock.bind(('', PORT))
    
    # Create the transport and protocol with our pre-made socket
    loop = asyncio.get_running_loop()
    transport, protocol = await loop.create_datagram_endpoint(ChatProtocol, sock=sock)

    # Wait for the connection to be closed/lost
    try:
        await protocol.on_con_lost
    finally:
        transport.close()


if __name__ == '__main__':
    asyncio.run(main())
