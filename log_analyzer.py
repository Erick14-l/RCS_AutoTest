# -*- coding: utf-8 -*-
"""
日志分析工具

此脚本用于分析RCS自动测试系统的日志文件，主要功能包括：
1. 统计网络连接成功次数
2. 检查DAS参数配置是否成功
3. 检查DCB连接状态
4. 检查数据接收状态
5. 检查各类错误信息
"""

import re
import sys
import os
from datetime import datetime

def analyze_log(log_file):
    # 初始化变量
    connection_count = 0
    das_config_success = True
    das_config_error_time = None
    das_config_steps = {
        "detector_init": {"sent": False, "received": False},
        "detector_set_das_count": {"sent": False, "received": False},
        "detector_config_das": {"sent": False, "received": False},
        "detector_set_das_param": {"sent": False, "received": False},
        "detector_set_work_mode": {"sent": False, "received": False},
        "detector_set_integral_time": {"sent": False, "received": False}
    }
    sfp_connect_before_start = None
    sfp_connect_after_start = None
    collect_flag_before_start = None
    collect_flag_after_start = None
    detector_start_time = None
    recv_zero = False
    recv_zero_time = None
    errors_215_217 = []
    errors_215_217_times = []
    errors_234 = []
    errors_234_times = []
    dcb_error_time = None
    has_error = False

    # 打开并读取日志文件
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 逐行分析日志
    for i, line in enumerate(lines):
        # 1. 检测网络连接成功
        if "成功连接到服务器" in line:
            connection_count += 1

        # 2. 检测DAS参数配置步骤
        for step in das_config_steps.keys():
            if f"发送: {step}" in line:
                das_config_steps[step]["sent"] = True
                # 记录时间戳，用于可能的错误报告
                if not das_config_steps[step]["received"]:
                    timestamp_match = re.search(r'\[(.*?)\]', line)
                    if timestamp_match:
                        das_config_error_time = timestamp_match.group(1)
            elif f"接收: {step}" in line:
                das_config_steps[step]["received"] = True

        # 3. 检测开始采集时间（用于判断DCB连接状态）
        if "发送: detector_start" in line:
            timestamp_match = re.search(r'\[(.*?)\]', line)
            if timestamp_match:
                detector_start_time = timestamp_match.group(1)

        # 4. 检查sfp_connet状态和collect_flag状态
        if "detail:" in line and "sfp_connet" in line:
            # 提取sfp_connet状态
            sfp_connect_match = re.search(r'detail:.+?sfp_connet\[(\d)\].+?collect_flag\[(\d)\]', line)
            if sfp_connect_match:
                sfp_connect_status = sfp_connect_match.group(1)
                collect_flag_status = sfp_connect_match.group(2)
                # 判断是在detector_start之前还是之后
                if detector_start_time is None:
                    sfp_connect_before_start = sfp_connect_status
                    collect_flag_before_start = collect_flag_status
                else:
                    sfp_connect_after_start = sfp_connect_status
                    collect_flag_after_start = collect_flag_status

        # 5. 检查recv是否为0
        if "recv:" in line and not "recv error" in line:
            recv_match = re.search(r'recv:(\d+)', line)
            if recv_match and recv_match.group(1) == '0':
                recv_zero = True
                # 记录时间戳
                timestamp_match = re.search(r'\[(.*?)\]', line)
                if timestamp_match:
                    recv_zero_time = timestamp_match.group(1)

        # 6. 检查215-217行的错误
        if "recv error:" in line or "sample error:" in line or "angle error:" in line:
            error_match = re.search(r'(recv error|sample error|angle error):(\d+)', line)
            if error_match and error_match.group(2) != '0':
                errors_215_217.append(line.strip())
                # 记录时间戳
                timestamp_match = re.search(r'\[(.*?)\]', line)
                if timestamp_match:
                    errors_215_217_times.append(timestamp_match.group(1))

        # 7. 检查234行的错误
        if "loss_view" in line and "err_view" in line and "total_view" in line:
            error_match = re.search(r'loss_view\[(\d+)\],err_view\[(\d+)\],total_view\[(\d+)\]', line)
            if error_match and (error_match.group(1) != '0' or error_match.group(2) != '0'):
                errors_234.append(line.strip())
                # 记录时间戳
                timestamp_match = re.search(r'\[(.*?)\]', line)
                if timestamp_match:
                    errors_234_times.append(timestamp_match.group(1))

    # 检查DAS参数配置是否成功
    for step, status in das_config_steps.items():
        if not status["sent"] or not status["received"]:
            das_config_success = False
            break

    # 输出分析结果
    print(f"日志文件: {log_file}")
    print("\n分析结果:")
    
    # 1. 打印网络连接成功次数
    print(f"\n1. 网络连接成功次数: {connection_count}")
    
    # 2. 打印DAS参数配置状态
    print("\n2. DAS参数配置状态:")
    if das_config_success:
        print("   DAS参数配置成功")
    else:
        print("   DAS参数配置失败")
        print(f"   错误发生时间: {das_config_error_time if das_config_error_time else '未知'}")
        for step, status in das_config_steps.items():
            print(f"   {step}: 发送[{'成功' if status['sent'] else '失败'}], 接收[{'成功' if status['received'] else '失败'}]")
        has_error = True
    
    # 3. 判断sfp_connet状态变化
    print("\n3. sfp_connet状态:")
    if sfp_connect_before_start and sfp_connect_after_start:
        if collect_flag_before_start == '0' and collect_flag_after_start == '1':
            print(f"   DCB连接正常: 采集前collect_flag={collect_flag_before_start}, 采集后collect_flag={collect_flag_after_start}")
        else:
            # 记录DCB连接失败的时间
            dcb_error_time = detector_start_time if detector_start_time else "未知"
            print(f"   DCB连接失败: collect_flag在开始采集前后变化异常 (采集前:{collect_flag_before_start}, 采集后:{collect_flag_after_start})")
            print(f"   错误发生时间: {dcb_error_time}")
            has_error = True
    else:
        print("   无法判断DCB连接状态: 未找到完整的sfp_connet状态信息")
        has_error = True
    
    # 4. 判断recv是否为0
    print("\n4. 数据接收状态:")
    if recv_zero:
        print("   无数据输入: recv为0")
        print(f"   错误发生时间: {recv_zero_time if recv_zero_time else '未知'}")
        has_error = True
    else:
        print("   数据接收正常")
    
    # 5. 打印215-217行的错误
    print("\n5. 错误检查(recv/sample/angle error):")
    if errors_215_217:
        for i, error in enumerate(errors_215_217):
            time_str = errors_215_217_times[i] if i < len(errors_215_217_times) else "未知"
            print(f"   {error}")
            print(f"   错误发生时间: {time_str}")
        has_error = True
    else:
        print("   未检测到错误")
    
    # 6. 打印234行的错误
    print("\n6. 错误检查(loss_view/err_view):")
    if errors_234:
        for i, error in enumerate(errors_234):
            time_str = errors_234_times[i] if i < len(errors_234_times) else "未知"
            print(f"   {error}")
            print(f"   错误发生时间: {time_str}")
        has_error = True
    else:
        print("   未检测到错误")
    
    # 7. 总结是否存在错误
    print("\n7. 总体状态:")
    if has_error:
        print("   存在错误")
    else:
        print("   未检测到错误")

def main():
    # 设置默认日志文件路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    default_log_file = os.path.join(current_dir, "logs", "2025-04-30_15-48-52.txt")
    
    if len(sys.argv) > 1:
        log_file = sys.argv[1]
    else:
        log_file = default_log_file
        print(f"使用默认日志文件: {log_file}")
    
    try:
        analyze_log(log_file)
    except Exception as e:
        print(f"分析过程中出错: {e}")

if __name__ == "__main__":
    main()