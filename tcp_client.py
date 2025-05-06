# 如果recv值为0，设置标志
#self.recv_zero_detected = True
                                                            
import socket
import time
import configparser
import threading
import queue
import os
from datetime import datetime

class TCPClient:
    def __init__(self, host='192.168.5.142', port=22001, reconnect_interval=5):
        self.host = host
        self.port = port
        self.reconnect_interval = reconnect_interval
        self.socket = None
        self.connected = False
        self.running = True
        self.send_queue = queue.Queue()
        self.current_command_index = 0
        self.commands = []
        # 创建日志文件
        self.log_file = self.create_log_file()
        # 标记是否是第一次连接
        self.is_first_connection = True
        # 添加重连标志
        self.reconnected = False
        # 添加锁，防止多线程同时修改命令索引
        self.command_index_lock = threading.Lock()
        # 添加标志，用于标记是否检测到异常情况
        self.recv_zero_detected = False
        self.error_detected = False
        self.load_commands()

    def load_commands(self):
        self.commands = []
        try:
            with open('sscom51.ini', 'r', encoding='gbk') as f:
                for line in f:
                    line = line.strip()
                    # 跳过注释和空行
                    if line.startswith(';') or not line:
                        continue
                    # 解析命令行
                    if line.startswith('N'):
                        parts = line.split('=', 1)
                        if len(parts) == 2:
                            cmd_parts = parts[1].split(',', 2)
                            if len(cmd_parts) >= 2:
                                # 只添加A类型的命令（ASCII字符串）且命令不为空
                                if cmd_parts[0] == 'A' and cmd_parts[1].strip():
                                    self.commands.append(cmd_parts[1].strip())
            # 确保关键命令存在于命令列表中
            self._ensure_critical_commands()
        except Exception as e:
            print(f"[{self.get_timestamp()}] 加载命令失败：{str(e)}")
            self.commands = []  # 如果加载失败，清空命令列表
            
    def _ensure_critical_commands(self):
        """确保关键命令存在于命令列表中，按照正确的顺序"""
        # 关键命令列表，按照执行顺序排列
        critical_commands = [
            "detector_init",
            "detector_set_das_count",
            "detector_config_das",
            "detector_set_das_param 0 2 0",
            "detector_set_work_mode 1 0 0",
            "detector_set_integral_time 600",
            "get_pcie_status",
            "detector_start"
        ]
        
        # 记录原始命令数量
        original_count = len(self.commands)
        
        # 检查每个关键命令是否存在，如果不存在则添加
        for i, cmd in enumerate(critical_commands):
            # 检查命令是否在整个命令列表中
            if cmd not in self.commands:
                # 如果命令不在命令列表中，则插入到适当位置
                insert_pos = min(i, len(self.commands))
                self.commands.insert(insert_pos, cmd)
                print(f"[{self.get_timestamp()}] 添加缺失的关键命令: {cmd}")
                self.write_log(f"添加缺失的关键命令: {cmd}")
            # 如果命令存在但不在前8个位置，确保它在正确的位置
            elif cmd in self.commands and self.commands.index(cmd) >= 8:
                # 先移除命令
                self.commands.remove(cmd)
                # 然后在正确位置插入
                insert_pos = min(i, len(self.commands))
                self.commands.insert(insert_pos, cmd)
                print(f"[{self.get_timestamp()}] 调整关键命令位置: {cmd}")
                self.write_log(f"调整关键命令位置: {cmd}")
        
        # 记录调整后的命令数量
        if len(self.commands) != original_count:
            cmd_msg = f"命令列表调整: 从 {original_count} 条调整为 {len(self.commands)} 条"
            print(f"[{self.get_timestamp()}] {cmd_msg}")
            self.write_log(cmd_msg)

    def connect(self):
        while self.running:
            try:
                if not self.connected:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket.connect((self.host, self.port))
                    self.connected = True
                    connect_msg = f"成功连接到服务器 {self.host}:{self.port}"
                    print(f"[{self.get_timestamp()}] {connect_msg}")
                    self.write_log(connect_msg)
                    
                    # 使用锁保护命令索引的修改
                    with self.command_index_lock:
                        # 重置命令索引，确保重连后从第一条命令开始
                        self.current_command_index = 0
                    
                    # 重新加载命令列表，确保所有命令都被加载
                    self.load_commands()
                    # 记录重新加载的命令数量
                    cmd_count_msg = f"重新加载了 {len(self.commands)} 条命令"
                    print(f"[{self.get_timestamp()}] {cmd_count_msg}")
                    self.write_log(cmd_count_msg)
                    
                    # 重置连接状态标记
                    self.is_first_connection = False
                    
                    # 设置重连标志，确保发送线程知道已经重连并从索引0开始
                    self.reconnected = True
                    
                    # 启动接收线程
                    receive_thread = threading.Thread(target=self.receive_data, daemon=True)
                    receive_thread.start()
                    
                    # 启动发送线程 - 每次连接成功后都会启动一个新的发送线程
                    # 该线程会在完成一个完整的命令循环或网络断开时自动结束
                    send_thread = threading.Thread(target=self.send_data, daemon=True)
                    send_thread.start()
                    
                    # 等待一小段时间，确保线程启动并处理重连标志
                    time.sleep(0.5)
                    
            except ConnectionRefusedError:
                error_msg = f"连接被拒绝，{self.reconnect_interval}秒后重试..."
                print(f"[{self.get_timestamp()}] {error_msg}")
                self.write_log(error_msg)
                time.sleep(self.reconnect_interval)
            except Exception as e:
                error_msg = f"连接错误：{str(e)}"
                print(f"[{self.get_timestamp()}] {error_msg}")
                self.write_log(error_msg)
                self.connected = False
                time.sleep(self.reconnect_interval)

    # 删除重复的__init__方法
        
    def send_data(self):
        # 添加一个标志，用于标记是否是重连后的第一次发送
        is_first_send_after_reconnect = True
        last_command_sent = None
        # 添加一个变量来跟踪已处理的命令，避免重复发送
        processed_command = False
        # 添加变量跟踪上一次打印的命令索引，避免重复打印
        last_printed_index = -1
        # 添加变量来跟踪命令循环是否完成
        cycle_completed = False
        
        while self.running and self.connected and not cycle_completed:
            try:
                # 如果检测到异常情况，则不发送任何命令，但保持TCP连接
                if self.recv_zero_detected or self.error_detected:
                    time.sleep(1.0)  # 等待1秒后再检查标志
                    continue
                    
                if self.connected and self.commands:
                    # 确保命令列表不为空
                    if not self.commands:
                        time.sleep(0.5)
                        continue
                    
                    # 使用锁保护命令索引的访问和修改
                    with self.command_index_lock:
                        # 检查重连标志，如果是重连后的第一次发送，确保从索引0开始
                        if self.reconnected:
                            self.current_command_index = 0
                            self.reconnected = False  # 重置标志
                            is_first_send_after_reconnect = True
                            processed_command = False  # 重置处理标志
                            last_printed_index = -1  # 重置上次打印的索引
                            
                        # 确保索引在有效范围内
                        if self.current_command_index >= len(self.commands):
                            self.current_command_index = 0
                            is_first_send_after_reconnect = True
                            processed_command = False  # 重置处理标志
                            last_printed_index = -1  # 重置上次打印的索引
                        
                        # 更新上次打印的索引为当前索引的实际值，使用整数值赋值
                        last_printed_index = int(self.current_command_index)
                        
                        # 获取当前命令
                        command = self.commands[self.current_command_index]
                        
                        # 保存当前命令索引，用于后续增加
                        current_index = self.current_command_index
                    
                    # 确保命令不为空且未被处理过
                    if command.strip() and not processed_command:
                        message = command + '\r\n'
                        self.socket.send(message.encode())
                        send_msg = f"发送: {command}"
                        print(f"[{self.get_timestamp()}] {send_msg}")
                        self.write_log(send_msg)
                        last_command_sent = command
                        processed_command = True  # 标记当前命令已处理
                    
                    # 等待响应处理完成
                    time.sleep(1.0)  # 增加等待时间，确保响应完全处理
                    
                    # 使用锁保护命令索引的修改
                    with self.command_index_lock:
                        # 只有当当前索引没有被其他线程修改时，才增加索引
                        if self.current_command_index == current_index and processed_command:
                            # 更新命令索引，确保每次只增加1
                            self.current_command_index += 1
                            processed_command = False  # 重置处理标志，准备处理下一条命令
                            
                            # 如果索引超出范围，标记循环完成并退出
                            if self.current_command_index >= len(self.commands):
                                self.current_command_index = 0
                                cycle_msg = "完成一个完整的命令循环，从头开始新的循环"
                                print(f"[{self.get_timestamp()}] {cycle_msg}")
                                self.write_log(cycle_msg)
                                # 标记循环完成
                                cycle_completed = True
                                break
                    
                    # 重置重连标志
                    is_first_send_after_reconnect = False
                    
                    # 从配置文件中读取发送间隔时间
                    time.sleep(2)  # 默认间隔2秒
            except Exception as e:
                error_msg = f"发送错误：{str(e)}"
                print(f"[{self.get_timestamp()}] {error_msg}")
                self.write_log(error_msg)
                self.connected = False
                # 记录断开连接时的命令索引
                disconnect_index_msg = f"断开连接时的命令索引: {self.current_command_index}"
                print(f"[{self.get_timestamp()}] {disconnect_index_msg}")
                self.write_log(disconnect_index_msg)
                # 不在这里重置命令索引，让connect方法处理
                break

    def receive_data(self):
        buffer = ""
        # 添加变量来跟踪当前命令和其回复
        current_command = None
        command_response_lines = []
        timestamp_prefix_len = 0
        response_timeout = 0.5  # 增加响应超时时间为500毫秒，确保完整接收响应
        last_data_time = 0
        # 添加变量来处理特殊命令的情况
        is_detector_temp = False
        detector_temp_data = ""
        # 记录上次断开连接时的命令索引
        last_disconnect_index = 0
        # 特殊命令列表，这些命令可能返回较多数据需要更长等待时间
        special_commands = ["detector_info", "detector_temp", "detector_state", "get_pcie_status", "get_img_handle_status"]
        
        while self.running:
            try:
                if self.connected:
                    # 检查是否有数据可读取，使用非阻塞模式
                    self.socket.setblocking(0)
                    try:
                        data = self.socket.recv(16384)  # 进一步增大接收缓冲区到16KB
                        last_data_time = time.time()
                        
                        if data:
                            # 将接收到的数据添加到缓冲区
                            buffer += data.decode('utf-8', errors='ignore')
                        else:
                            raise ConnectionError("Connection closed by server")
                    except BlockingIOError:
                        # 没有数据可读取，检查是否需要处理缓冲区中的数据
                        # 对于特殊命令，增加等待时间以确保完整接收
                        if current_command in special_commands:
                            response_wait_time = 0.5  # 为特殊命令增加等待时间到500毫秒
                        else:
                            response_wait_time = response_timeout
                            
                        if buffer and (time.time() - last_data_time > response_wait_time):
                            # 如果超过等待时间没有新数据，处理当前缓冲区
                            self._process_buffer(buffer, current_command, command_response_lines, timestamp_prefix_len)
                            buffer = ""
                            current_command = None
                            command_response_lines = []
                        time.sleep(0.01)  # 短暂休眠，避免CPU占用过高
                        continue
                    
                    # 处理缓冲区中的完整消息
                    if '\n' in buffer:
                        lines = buffer.split('\n')
                        # 保留最后一个可能不完整的行
                        buffer = lines.pop()
                        
                        # 检查是否正在处理detector_temp命令
                        if is_detector_temp and lines:
                            # 继续收集detector_temp的数据
                            for line in lines:
                                if line.strip():
                                    detector_temp_data += " " + line.strip()
                            # 如果有足够的数据（包含high_board_temp），则处理并输出
                            if "high_board_temp" in detector_temp_data or len(detector_temp_data) > 200:
                                # 打印和记录完整的温度数据
                                print(f"{' ' * timestamp_prefix_len}{detector_temp_data}")
                                self.write_log(detector_temp_data)
                                is_detector_temp = False
                                detector_temp_data = ""
                                continue
                        
                        # 检查是否是新命令的回复
                        if lines and lines[0].strip():
                            first_line = lines[0].strip()
                            command_name = first_line.split(' ')[0] if ' ' in first_line else first_line
                            
                            # 检查是否是需要特殊处理的命令
                            if command_name in special_commands:
                                # 为特殊命令处理，确保完整接收所有信息
                                is_detector_temp = command_name == "detector_temp"  # 只有detector_temp命令设置此标志
                                
                                # 为第一行添加时间戳和接收标志
                                timestamp = self.get_timestamp()
                                recv_msg = f"接收: {first_line}"
                                timestamp_prefix = f"[{timestamp}] "
                                timestamp_prefix_len = len(timestamp_prefix)
                                
                                print(f"{timestamp_prefix}{recv_msg}")
                                self.write_log(recv_msg)
                                
                                # 收集所有响应行并等待更长时间确保完整接收
                                time.sleep(0.3)  # 额外等待300ms确保接收完整
                                
                                # 尝试接收更多数据
                                try:
                                    self.socket.setblocking(0)
                                    more_data = b""
                                    try_count = 0
                                    while try_count < 5:  # 最多尝试5次
                                        try:
                                            chunk = self.socket.recv(16384)  # 使用更大的缓冲区
                                            if chunk:
                                                more_data += chunk
                                                last_data_time = time.time()
                                            else:
                                                break
                                        except BlockingIOError:
                                            time.sleep(0.1)
                                            try_count += 1
                                            continue
                                    
                                    if more_data:
                                        more_lines = more_data.decode('utf-8', errors='ignore').split('\n')
                                        lines.extend([l for l in more_lines if l.strip()])
                                except Exception as e:
                                    print(f"{' ' * timestamp_prefix_len}接收额外数据时出错: {str(e)}")
                                
                                # 处理所有行
                                if len(lines) > 1:
                                    # 分行处理响应，确保每行都有正确的缩进和日志记录
                                    for resp_line in lines[1:]:
                                        if resp_line.strip():
                                            print(f"{' ' * timestamp_prefix_len}{resp_line.strip()}")
                                            self.write_log(resp_line.strip())
                                            
                                            # 检查是否是get_img_handle_status命令的响应
                                            if command_name == "get_img_handle_status":
                                                # 检查recv值
                                                if resp_line.strip().startswith("recv:"):
                                                    try:
                                                        # 提取recv值
                                                        recv_value = int(resp_line.strip().split(":")[1].strip())
                                                        # 如果recv值为0，设置标志
                                                        if recv_value == 0:
                                                            #self.recv_zero_detected = True
                                                            self.recv_zero_detected = False
                                                            # 记录无数据输入信息
                                                            no_data_msg = "无数据输入"
                                                            print(f"[{self.get_timestamp()}] {no_data_msg}")
                                                            self.write_log(no_data_msg)
                                                        else:
                                                            # 如果recv值不为0，重置标志
                                                            self.recv_zero_detected = False
                                                    except ValueError:
                                                        pass
                                                
                                                # 检查error值
                                                elif resp_line.strip().startswith("recv error:"):
                                                    try:
                                                        error_value = int(resp_line.strip().split(":")[1].strip())
                                                        if error_value != 0:
                                                            self.error_detected = True
                                                            # 记录存在错误信息
                                                            error_msg = "存在错误"
                                                            print(f"[{self.get_timestamp()}] {error_msg}")
                                                            self.write_log(error_msg)
                                                    except ValueError:
                                                        pass
                                                
                                                # 检查sample error
                                                elif resp_line.strip().startswith("sample error:"):
                                                    try:
                                                        error_value = int(resp_line.strip().split(":")[1].strip())
                                                        if error_value != 0:
                                                            self.error_detected = True
                                                            # 记录存在错误信息
                                                            error_msg = "存在错误"
                                                            print(f"[{self.get_timestamp()}] {error_msg}")
                                                            self.write_log(error_msg)
                                                    except ValueError:
                                                        pass
                                                
                                                # 检查angle error
                                                elif resp_line.strip().startswith("angle error:"):
                                                    try:
                                                        error_value = int(resp_line.strip().split(":")[1].strip())
                                                        if error_value != 0:
                                                            self.error_detected = True
                                                            # 记录存在错误信息
                                                            error_msg = "存在错误"
                                                            print(f"[{self.get_timestamp()}] {error_msg}")
                                                            self.write_log(error_msg)
                                                        else:
                                                            # 如果所有error值都为0，重置错误标志
                                                            if not self.error_detected:
                                                                self.error_detected = False
                                                    except ValueError:
                                                        pass
                                
                                # 添加一个空行，使输出更清晰
                                print("")
                                
                                # 如果是detector_temp命令，不需要继续处理
                                if is_detector_temp:
                                    is_detector_temp = False
                                    detector_temp_data = ""
                                    
                                # 处理完特殊命令后，清空缓冲区和当前命令
                                buffer = ""
                                current_command = None
                                continue  # 继续下一次循环，避免重复处理
                            
                            # 检查是否是detector_temp命令
                            elif command_name == "detector_temp":
                                is_detector_temp = True
                                detector_temp_data = first_line
                                # 为第一行添加时间戳和接收标志
                                timestamp = self.get_timestamp()
                                recv_msg = f"接收: {first_line}"
                                timestamp_prefix = f"[{timestamp}] "
                                timestamp_prefix_len = len(timestamp_prefix)
                                
                                print(f"{timestamp_prefix}{recv_msg}")
                                self.write_log(recv_msg)
                                
                                # 收集detector_temp的所有响应行
                                if len(lines) > 1:
                                    for line in lines[1:]:
                                        if line.strip():
                                            detector_temp_data += " " + line.strip()
                                    # 打印和记录完整的温度数据
                                    print(f"{' ' * timestamp_prefix_len}{detector_temp_data}")
                                    self.write_log(detector_temp_data)
                                    is_detector_temp = False
                                    detector_temp_data = ""
                            # 如果是新命令，立即处理之前的响应并开始新的响应
                            elif current_command != command_name:
                                # 处理之前命令的回复（如果有）
                                if command_response_lines:
                                    self._process_command_response(command_response_lines, timestamp_prefix_len)
                                    command_response_lines = []
                                    # 添加一个空行，使输出更清晰
                                    print("")
                                
                                current_command = command_name
                                
                                # 为第一行添加时间戳和接收标志
                                timestamp = self.get_timestamp()
                                recv_msg = f"接收: {first_line}"
                                timestamp_prefix = f"[{timestamp}] "
                                timestamp_prefix_len = len(timestamp_prefix)
                                
                                print(f"{timestamp_prefix}{recv_msg}")
                                self.write_log(recv_msg)
                                
                                # 添加一个空行，使输出更清晰
                                print("")
                                
                                # 立即处理剩余行
                                if len(lines) > 1:
                                    remaining_lines = lines[1:]
                                    if remaining_lines:
                                        self._process_command_response(remaining_lines, timestamp_prefix_len)
                            else:
                                # 同一命令的后续回复，立即处理
                                self._process_command_response(lines, timestamp_prefix_len)
                        else:
                            # 空行或没有行，如果有当前命令，则作为其响应处理
                            if current_command and lines:
                                self._process_command_response(lines, timestamp_prefix_len)
                    
                    # 如果缓冲区过大但没有换行符，可能是一个大消息，直接处理
                    elif len(buffer) > 4096:
                        timestamp = self.get_timestamp()
                        recv_msg = f"接收: {buffer}"
                        timestamp_prefix = f"[{timestamp}] "
                        timestamp_prefix_len = len(timestamp_prefix)
                        
                        print(f"{timestamp_prefix}{recv_msg}")
                        self.write_log(recv_msg)
                        buffer = ""
            except ConnectionError as e:
                error_msg = f"连接错误：{str(e)}"
                print(f"[{self.get_timestamp()}] {error_msg}")
                self.write_log(error_msg)
                self.connected = False
                break
            except Exception as e:
                error_msg = f"接收错误：{str(e)}"
                print(f"[{self.get_timestamp()}] {error_msg}")
                self.write_log(error_msg)
                self.connected = False
                break
                
    def _process_buffer(self, buffer, current_command, command_response_lines, timestamp_prefix_len):
        """处理缓冲区中的数据"""
        if not buffer.strip():
            return
            
        lines = buffer.strip().split('\n')
        if not lines:
            return
            
        # 第一行作为命令名
        first_line = lines[0].strip()
        timestamp = self.get_timestamp()
        recv_msg = f"接收: {first_line}"
        timestamp_prefix = f"[{timestamp}] "
        timestamp_prefix_len = len(timestamp_prefix)
        
        print(f"{timestamp_prefix}{recv_msg}")
        self.write_log(recv_msg)
        
        # 处理剩余行
        if len(lines) > 1:
            self._process_command_response(lines[1:], timestamp_prefix_len)

    def get_timestamp(self):
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
    def _process_command_response(self, response_lines, timestamp_prefix_len):
        """处理命令的多行响应，只为第一行添加时间戳和接收标志，其余行省略时间戳和接收标志并左对齐显示"""
        # 跳过空行
        response_lines = [line.strip() for line in response_lines if line.strip()]
        if not response_lines:
            return
            
        # 创建与时间戳前缀长度相同的空白字符串，用于对齐后续行
        alignment_prefix = ' ' * timestamp_prefix_len
        
        # 处理每一行响应
        for line in response_lines:
            # 打印对齐的行，不带时间戳前缀和接收标志
            print(f"{alignment_prefix}{line}")
            # 记录到日志文件，不带接收标志
            self.write_log(line)
        
        # 添加一个空行，使输出更清晰
        print("")
        
    def create_log_file(self):
        # 创建logs目录（如果不存在）
        if not os.path.exists('logs'):
            os.makedirs('logs')
        # 生成日志文件名（使用当前日期和时间）
        filename = f"logs/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        return filename
        
    def write_log(self, message):
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{self.get_timestamp()}] {message}\n")

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass

def main():
    # 创建TCP客户端实例
    client = TCPClient(host='192.168.5.142', port=22001)
    
    try:
        # 开始连接
        client.connect()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
        client.stop()

if __name__ == '__main__':
    main()