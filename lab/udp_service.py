"""Local UDP transport and recovery of a stopped receiver during hot reload."""
import socket
import threading


def receive_loop(service):
    while not service.closed.is_set():
        try:
            data, addr = service.sock.recvfrom(65535)
        except socket.timeout:
            continue
        except ConnectionResetError:
            # Windows reports an ICMP error from a departed peer on recvfrom.
            # It does not mean that the listening socket has been closed.
            service.lab.event('udp_peer_reset', {'channel':service.channel})
            continue
        except OSError as exc:
            if not service.closed.is_set():
                service.lab.event('udp_listener_stopped', {
                    'channel':service.channel,'error':str(exc)})
            break
        try:
            service.lab.record_udp(service.channel,'C2S',data)
            with service.protocol_lock:
                responses = service.protocol.handle(data,addr)
            for response in responses:
                service.sock.sendto(response,addr)
                service.lab.record_udp(service.channel,'S2C',response)
        except Exception as exc:
            service.lab.event('protocol_error',
                f'{service.channel}: {type(exc).__name__}: {exc}')


def repair_dead_listener(service):
    """Explicit protocol hot reload can revive an open socket's dead thread.

    Also accepts the old app.UdpService instance during an in-process upgrade.
    A live receiver or intentionally stopped service is never replaced.
    """
    if service is None or service.closed.is_set() or service.thread.is_alive():
        return False
    if service.sock.fileno()<0:
        return False
    service.thread=threading.Thread(target=receive_loop,args=(service,),daemon=True)
    service.thread.start()
    service.lab.event('udp_listener_recovered',{'channel':service.channel,
        'port':service.port,'socket_preserved':True})
    return True


class UdpService:
    def __init__(self, port, protocol, channel, lab):
        self.protocol,self.channel,self.lab=protocol,channel,lab
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1',port))
        self.port=self.sock.getsockname()[1]
        self.sock.settimeout(.2)
        self.closed=threading.Event()
        self.protocol_lock=threading.RLock()
        self.thread=threading.Thread(target=receive_loop,args=(self,),daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.closed.set()
        self.sock.close()
        self.thread.join(timeout=1)
