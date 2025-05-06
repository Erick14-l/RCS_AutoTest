# TCP客户端自动化通信工具

这是一个基于Python的TCP客户端工具，用于自动化发送和接收数据。它支持自动重连、循环发送数据串，并能记录通信日志。

## 功能特点

- TCP客户端自动连接和重连
- 支持读取sscom51.ini格式的数据串配置
- 按顺序循环发送多条数据串
- 自动断线重连，并从头开始重新发送
- 支持显示接收数据的时间戳
- 支持数据分包显示
- 自动检测和添加关键命令，确保命令按正确顺序执行
- 特殊命令处理（detector_info, detector_temp, detector_state等）
- 监控接收数据功能，当检测到recv值为0时暂停发送但保持连接
- 自动创建日期时间格式的日志文件，记录所有通信过程

## 使用方法

1. 安装Python 3.x
2. 安装依赖包：
   ```
   pip install configparser
   ```

3. 配置连接参数：
   - 编辑 `config.ini` 文件，设置目标主机IP和端口
   - 编辑 `sscom51.ini` 文件，配置要发送的数据串

4. 运行程序：
   ```
   python tcp_client.py
   ```

## 配置文件说明

### config.ini

```ini
[Connection]
host = 192.168.8.81        # 目标主机IP
port = 22001               # 目标主机端口
reconnect_interval = 5     # 重连间隔（秒）

[SendSettings]
interval = 1000           # 发送间隔（毫秒）
add_newline = yes         # 是否添加换行符
show_timestamp = yes      # 是否显示时间戳
show_packages = yes       # 是否显示分包
```

### sscom51.ini

按照以下格式配置数据串：
```ini
N1=A,command1    # 第1条命令
N2=A,command2    # 第2条命令
# ... 依此类推
```

## 注意事项

1. 确保目标主机IP和端口配置正确
2. 程序会自动处理连接断开的情况
3. 使用Ctrl+C可以终止程序运行
4. 程序会自动检查并添加关键命令，确保它们按正确顺序执行
5. 当检测到接收数据为0时，程序会暂停发送命令但保持TCP连接
6. 所有通信日志会保存在logs目录下，文件名格式为：YYYY-MM-DD_HH-MM-SS.txt