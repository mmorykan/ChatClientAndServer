import argparse
import asyncio
import struct
import time
"""
This program can be run as a chat server or a chat client using the TCP server-client protocol.
"""

PORT = 2568

async def recv_formatted_data(reader, frmt):
    """
    Receives struct-formatted data according to the struct format given and
    returns a tuple of values.
    """
    return struct.unpack(frmt, await reader.read(struct.calcsize(frmt)))


async def recv_single_value(reader, frmt):
    """
    Receives a single value according to the struct format given and returns it.
    """
    return (await recv_formatted_data(reader, frmt))[0]


async def recv_str(reader):
    """
    Receives the length of the string being sent and then receives that many bytes and returns that byte string decoded
    """
    length = await recv_single_value(reader, '<i')
    data = await reader.read(length)
    return data.decode()


async def recv_str_list(reader):
    """
    Receives the length of the list being sent. Then receives each string in the list and appends each string to a list.
    """
    length = await recv_single_value(reader, '<i')
    message_list = []
    for i in range(length):
        message_list.append(await recv_str(reader))
    
    return message_list


async def recv_list_of_lists(reader):
    """
    Receives a list of lists by receiving the length of the list first and then receiving each sub-list separately 
    """
    length = await recv_single_value(reader, '<i')
    message_list = []
    for i in range(length):
        message_list.append(await recv_str_list(reader))

    return message_list


def send_str(writer, string):
    """
    Encodes the string, packs the string with the length first. Then sends the string with length first
    """
    string = string.encode()
    data = struct.pack('<i', len(string))
    data += struct.pack(str(len(string)) + 's', string)
    writer.write(data)


def send_str_list(writer, strings):
    """
    Packs the length of the list and sends it. Then sends each string within the list separately
    """
    data = struct.pack('<i', len(strings))
    writer.write(data)
    for string in strings:
        send_str(writer, string)


def send_list_of_lists(writer, messages):
    """
    Sends a list of lists by packing and sending the length of the list first. 
    This is what is used to send the ten most recent messages to the clients
    """
    data = struct.pack('<i', len(messages))
    writer.write(data)
    for message in messages:
        send_str_list(writer, message)


class TCPServerClient:
    def __init__(self):
        self.messages = []
        self.people = {}


    def send_messages_to_all(self, message):
        """
        Iterates over the list of writers and uses each writer to send the message to that connected client
        """
        for writer in self.people.values():
            send_str_list(writer, message)


    def add_to_recent_messages(self, message_list):
        """
        Adds the recent message to the ten most recent messages list
        """
        if len(self.messages) == 10:
            self.messages.pop(0)

        self.messages.append(message_list)


    async def client_send_username(self, writer):
        """
        Sends a 1 to the server indicating a username will be sent.
        Sends a username to the server.
        """
        loop = asyncio.get_running_loop()
        writer.write(struct.pack('<i', 1))
        username = await loop.run_in_executor(None, lambda: input('Enter username: '))
        send_str(writer, username)
        
    
    async def client_get_recent_messages(self, reader):
        """
        Client receives the most recent messagse (up to 10) and prints them out
        """
        recent_messages = await recv_list_of_lists(reader)
        for message in recent_messages:
            print(' '.join(message))


    def new_connection(self, writer, username):
        """
        Appends a new user to the client list
        Sends the recent messages list
        Appends the current writer to the writers list
        """
        self.people[username] = writer
        send_list_of_lists(writer, self.messages)
        

    async def server_get_username_validation(self, reader, writer):
        """
        Receives the username from the client
        Sets up new connection if the username does not already exist
        """
        username = await recv_str(reader)
        if username not in self.people.keys():
            writer.write(struct.pack('<?', True))
            self.new_connection(writer, username)
            return username

        writer.write(struct.pack('<?', False))        
        return False


    async def server_receive_messages(self, reader, writer, valid_username):
        """
        Server receives messages
        If client has left chat room, writer is removed from writers list and client's username is removed from the username list
        """
        try:
            return await recv_str(reader)
        except:
            del self.people[valid_username]
            return False


    async def read_from_server(self, reader):
        """
        This client function reads username validation from the server, receives the ten most recent messages, 
        and constantly attempts to receive messages
        """
        valid_username = await recv_single_value(reader, '<?')
        if valid_username:
            await self.client_get_recent_messages(reader)

        while valid_username:
            message = await recv_str_list(reader)
            print(' '.join(message))


    async def write_to_server(self, writer):
        """
        This function performs all the writing to the server. It sends the username first and then constantly asked for input afterwards
        """
        loop = asyncio.get_running_loop()
        await self.client_send_username(writer)

        while True:
            writer.write(struct.pack('<i', 2))
            data = await loop.run_in_executor(None, input)
            send_str(writer, data)

        
    async def client_connect(self, address):
        """
        Runs the whole client protocol.
        Constantly asks for input, sends messages, sends the username, and receives the ten most recent messages.
        """
        reader, writer = await asyncio.open_connection(address, 2568)

        
        client_write = asyncio.create_task(self.write_to_server(writer))
        client_read = asyncio.create_task(self.read_from_server(reader))
    
        await client_write
        await client_read


    async def server_handle_clients(self, reader, writer):
        """
        Runs the whole server protocol
        Obtains a 1 or 2 from the client.
        Decides if the client has given a valid username and sends the ten most recent messages
        Receives messages from the client and distributes them back to all connected clients
        Logs the ten most recent messages and saves the IP addresses of each client 
        """
        valid_username = False
        while True:
            loop = asyncio.get_running_loop()
            data = await recv_single_value(reader, '<i')

            if data == 1 and not valid_username:
                valid_username = await self.server_get_username_validation(reader, writer)

            if valid_username:
                if data == 2:
                    message = await self.server_receive_messages(reader, writer, valid_username)

                    if not message and message != '':
                        break                   

                    self.add_to_recent_messages([time.strftime('%X'), valid_username, message])
                    self.send_messages_to_all(self.messages[-1])
                
            else:
                break
        
        await writer.drain()
        writer.close()


    async def run_server(self, port):
        """
        Runs the server forever using server_hand_clients() as the callback
        """
        server = await asyncio.start_server(self.server_handle_clients, '', port)
        async with server:
            await server.serve_forever()


async def main():
    """
    Parses all arguments from the command line and either runs the server or runs the client based on command line input
    """
    parser = argparse.ArgumentParser(description='TCP server-client Chat Room that runs on port 2568')
    subparsers = parser.add_subparsers(title='command', dest='cmd', required=True)
    subparsers.add_parser(name='server', description='Run the server')

    client = subparsers.add_parser(name='client', description='Connect to server chat room')
    client.add_argument('address', help='The IP address of the server')
    args = parser.parse_args()

    connection = TCPServerClient()

    if args.cmd == 'server':
        await connection.run_server(PORT)
    elif args.cmd == 'client':
        await connection.client_connect(args.address)


if __name__ == '__main__':
    asyncio.run(main())

