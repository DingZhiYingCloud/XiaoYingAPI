1. 先看看有哪些服务器、是否在线：
   {"action":"list_agents"}

2. 让某些服务器去做一件事（最常用）。task 用大白话写，子 agent 会自己在本地完成并回报结论：
   {"action":"dispatch","agents":"all","task":"看看磁盘和内存还剩多少"}
   {"action":"dispatch","agents":["server-1","server-2"],"task":"查一下 nginx 状态，异常就给出原因"}

3. 在本机（大脑所在那台机器）执行一条命令：
   {"action":"run_local","cmd":"df -h"}
