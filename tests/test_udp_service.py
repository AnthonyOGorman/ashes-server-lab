import socket
import threading
import unittest
from types import SimpleNamespace
from lab.udp_service import UdpService, receive_loop, repair_dead_listener


class UdpServiceTests(unittest.TestCase):
    def lab(self):
        return SimpleNamespace(event=lambda *args:None,record_udp=lambda *args:None)

    def test_peer_reset_does_not_stop_next_packet(self):
        closed=threading.Event();handled=[]
        class Socket:
            calls=0
            def recvfrom(self, size):
                self.calls+=1
                if self.calls==1:raise ConnectionResetError(10054,'departed peer')
                closed.set();return b'new peer',('127.0.0.1',1234)
        service=SimpleNamespace(closed=closed,sock=Socket(),lab=self.lab(),
            channel='world',protocol_lock=threading.RLock(),
            protocol=SimpleNamespace(handle=lambda data,addr:handled.append(data) or []))
        receive_loop(service)
        self.assertEqual(handled,[b'new peer'])

    def test_record_failure_does_not_kill_receiver(self):
        closed=threading.Event();handled=[]
        class Socket:
            calls=0
            def recvfrom(self,size):
                self.calls+=1
                if self.calls==2:closed.set()
                return b'data',('127.0.0.1',1234)
        lab=self.lab();calls=[]
        def record(*args):
            calls.append(args)
            if len(calls)==1:raise RuntimeError('record failed')
        lab.record_udp=record
        service=SimpleNamespace(closed=closed,sock=Socket(),lab=lab,channel='world',
            protocol_lock=threading.RLock(),
            protocol=SimpleNamespace(handle=lambda data,addr:handled.append(data) or []))
        receive_loop(service)
        self.assertEqual(handled,[b'data'])

    def test_dead_receiver_recovers_on_same_socket_and_live_receiver_is_preserved(self):
        service=UdpService(0,SimpleNamespace(handle=lambda data,addr:[b'reply']),
                           'world',self.lab())
        client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(2)
        try:
            # An unstarted thread is dead; this models the legacy stopped loop.
            self.assertTrue(repair_dead_listener(service))
            thread=service.thread
            self.assertFalse(repair_dead_listener(service))
            self.assertIs(service.thread,thread)
            client.sendto(b'probe',('127.0.0.1',service.port))
            self.assertEqual(client.recvfrom(100)[0],b'reply')
        finally:
            client.close();service.stop()
        self.assertFalse(repair_dead_listener(service))
