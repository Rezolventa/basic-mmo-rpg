from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any

from websockets.asyncio.client import connect

from basic_mmo_rpg.domain.movement import MovementIntent
from basic_mmo_rpg.shared.protocol import (
    ClientMessageType,
    ProtocolError,
    ProtocolMessage,
    decode_message,
    encode_message,
    movement_intent_to_payload,
)


class NetworkClient:
    """
    Запускает websocket-клиент в фоновом потоке для pygame-фронтенда.
    """

    def __init__(
        self,
        server_url: str,
        send_rate: float = 30.0,
        reconnect_delay: float = 1.0,
    ) -> None:
        """
        Инициализирует сетевые очереди, настройки таймингов и потокобезопасное состояние.
        """
        self.server_url = server_url
        self.send_rate = send_rate
        self.reconnect_delay = reconnect_delay
        self._incoming: queue.Queue[ProtocolMessage] = queue.Queue()
        self._latest_intent = MovementIntent()
        self._intent_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._connected = False
        self._status = "disconnected"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """
        Запускает фоновый сетевой поток, если он еще не работает.
        """
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="mmo-network-client",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """
        Просит сетевой поток остановиться и недолго ждет его завершения.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def send_movement_intent(self, intent: MovementIntent) -> None:
        """
        Сохраняет последнее намерение движения для фонового цикла отправки.
        """
        with self._intent_lock:
            self._latest_intent = intent

    def drain_messages(self) -> list[ProtocolMessage]:
        """
        Возвращает все протокольные сообщения, полученные с прошлого чтения очереди.
        """
        messages: list[ProtocolMessage] = []
        while True:
            try:
                messages.append(self._incoming.get_nowait())
            except queue.Empty:
                return messages

    def is_connected(self) -> bool:
        """
        Возвращает, открыто ли websocket-соединение в данный момент.
        """
        with self._status_lock:
            return self._connected

    def status(self) -> str:
        """
        Возвращает человекочитаемый текст сетевого статуса.
        """
        with self._status_lock:
            return self._status

    def _thread_main(self) -> None:
        """
        Запускает asyncio-точку входа websocket-клиента внутри сетевого потока.
        """
        asyncio.run(self._run_until_stopped())

    async def _run_until_stopped(self) -> None:
        """
        Переподключается к websocket-серверу, пока клиент не остановлен.
        """
        while not self._stop_event.is_set():
            try:
                self._set_status(connected=False, status="connecting")
                async with connect(self.server_url) as websocket:
                    self._set_status(connected=True, status="connected")
                    sender = asyncio.create_task(self._send_loop(websocket))
                    receiver = asyncio.create_task(self._receive_loop(websocket))
                    done, pending = await asyncio.wait(
                        {sender, receiver},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    for task in done:
                        task.result()
            except Exception as exc:
                if not self._stop_event.is_set():
                    self._set_status(connected=False, status=f"network error: {exc}")
                    await asyncio.sleep(self.reconnect_delay)
            finally:
                self._set_status(connected=False, status="disconnected")

    async def _send_loop(self, websocket: Any) -> None:
        """
        Периодически отправляет последнее намерение движения на сервер.
        """
        interval = 1.0 / self.send_rate
        while not self._stop_event.is_set():
            message = ProtocolMessage(
                type=ClientMessageType.MOVE_REQUESTED,
                payload=movement_intent_to_payload(self._current_intent()),
            )
            await websocket.send(encode_message(message))
            await asyncio.sleep(interval)

    async def _receive_loop(self, websocket: Any) -> None:
        """
        Получает протокольные сообщения от сервера и кладет их в очередь для pygame.
        """
        async for raw_message in websocket:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")
            try:
                self._incoming.put(decode_message(raw_message))
            except (ProtocolError, UnicodeDecodeError):
                continue

    def _current_intent(self) -> MovementIntent:
        """
        Потокобезопасно возвращает последнее намерение движения.
        """
        with self._intent_lock:
            return self._latest_intent

    def _set_status(self, connected: bool, status: str) -> None:
        """
        Потокобезопасно обновляет поля состояния соединения.
        """
        with self._status_lock:
            self._connected = connected
            self._status = status
