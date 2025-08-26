import socket
import struct
import time

# ▼▼▼【変更点】▼▼▼
# IPアドレスをPC内部を示す '127.0.0.1' に変更
HOST = '127.0.0.1'
# ▲▲▲【変更点】▲▲▲
PORT = 60200

def parse_command_packet(packet: bytes):
    """12バイトのコマンドパケットを解析して内容を表示する"""
    if len(packet) != 12:
        print(f"  [エラー] 受信したパケット長が12バイトではありません ({len(packet)} bytes)")
        return None

    values = struct.unpack('!BBBBBBBBBBBB', packet)
    
    op_code = values[0]
    command_id = values[2]
    offset = (values[3] << 16) + (values[4] << 8) + values[5]
    data_size = (values[6] << 16) + (values[7] << 8) + values[8]

    print("--- 受信コマンドパケット解析結果 ---")
    print(f"  オペレーションコード: {hex(op_code)}")
    print(f"  コマンドID: {command_id}")
    print(f"  オフセット: {offset}")
    print(f"  データサイズ: {data_size}")
    print("------------------------------------")
    
    return op_code, data_size

print(f"模擬制御基板サーバーを起動します...")
print(f"IPアドレス {HOST}:{PORT} で待機中...")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.bind((HOST, PORT))
    s.listen()

    try:
        while True:
            conn, addr = s.accept()
            with conn:
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] クライアント {addr} から接続がありました。")

                command_packet = conn.recv(12)
                if not command_packet:
                    continue
                
                print(f"1. 12バイトのコマンドパケットを受信しました。")
                parsed_info = parse_command_packet(command_packet)

                if parsed_info:
                    op_code, data_size = parsed_info
                    
                    if op_code == 0x3B and data_size > 0:
                        print(f"2. 書き込みコマンドのため、{data_size} バイトのデータパケットを受信します。")
                        
                        received_data = b''
                        while len(received_data) < data_size:
                            remaining = data_size - len(received_data)
                            chunk = conn.recv(min(remaining, 4096))
                            if not chunk:
                                break
                            received_data += chunk
                        
                        print(f"   -> {len(received_data)} バイトのデータを受信完了。")
                        print(f"   -> 受信データ(先頭64バイト): {received_data[:64]}")

                    print("3. 4バイトのステータスパケット (0x00000000) をクライアントに返信します。")
                    status_packet = struct.pack('!I', 0)
                    conn.sendall(status_packet)
                    print("   -> 返信完了。")

                print("クライアントとの通信を終了し、接続を閉じました。")

    except KeyboardInterrupt:
        print("\nCtrl+C が押されました。サーバーを終了します。")