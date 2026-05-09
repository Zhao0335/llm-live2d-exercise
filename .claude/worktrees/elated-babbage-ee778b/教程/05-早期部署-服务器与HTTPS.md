# 第 5 章：早期部署 —— 服务器与 HTTPS

> 第 4 章结束时，我们有一个本地能跑的聊天应用。这章不加新功能，而是把它部署到真实服务器上。听起来像是可以推迟的事，但我们故意放在这里——越早做越省事。

---

## 5.1 为什么现在就要部署

很多教程把部署放在最后一章。结果学完一路，回头看代码，发现到处是 `localhost:8000`——得全部改。WebSocket 地址是 `ws://`，服务器上要换成 `wss://`。本地没有 HTTPS，服务器有，又有一堆地方要改。

更糟的是：你在本地测试过的每一章，都没有在真实服务器上验证过。等到最后才部署，问题全堆在一起，排查起来很痛苦。

我们换一种做法：**第 4 章跑通之后，立刻部署一次**。然后从第 6 章开始，每章的新功能都直接在真实服务器上验证。更新代码只需要 `git push`，然后在服务器上 `git pull + 重启`，三十秒搞定。

关键是在代码里做好"环境感知"——同一套代码，本地跑时自动用 `localhost`，服务器上跑时自动用真实域名。这个配置今天做一次，后面所有章节直接沿用。

---

## 5.2 选一台服务器

各大云厂商（阿里云、腾讯云、华为云）对新用户都有优惠套餐，大概 99 元/年，配置选 **2 核 2G 内存、40G 硬盘，Ubuntu 22.04 系统**，这个项目完全够用。

买好之后，你会得到一个公网 IP 地址。用 SSH 连上去：

```
ssh root@你的服务器公网IP
```

第一次连接会提示确认密钥指纹，输入 `yes`，然后输入密码。如果能看到命令行提示符，说明连上了。

> **试一下**：连上服务器之后，运行 `uname -a`，确认是 Ubuntu 系统；运行 `free -h`，看看内存够不够。

---

## 5.3 服务器初始化

刚拿到的服务器，先做两件事：更新系统，安装必要的工具。

```bash
apt update && apt upgrade -y
apt install -y git nginx certbot python3-certbot-nginx python3.12 python3.12-venv
```

这里安装了：Git（代码同步）、Nginx（反向代理）、certbot（免费 HTTPS 证书）、Python 3.12。安装过程可能要几分钟，等它完成。

---

## 5.4 把代码用 Git 管理起来

**在本地**，进入 `my-live2d` 文件夹，初始化 Git 仓库：

```bash
git init
git add .
git commit -m "第一版：HTTP 聊天跑通"
```

还需要一个 `.gitignore` 文件，告诉 Git 哪些东西不要提交——虚拟环境、Python 缓存、`.env` 配置文件、生成的音频文件，都不应该进代码库：

```
venv/
__pycache__/
*.pyc
.env
*.mp3
*.wav
chat.db
```

然后去 GitHub 新建一个仓库，把代码推上去：

```bash
git remote add origin https://github.com/你的用户名/my-live2d.git
git push -u origin main
```

**在服务器上**，把代码拉下来：

```bash
git clone https://github.com/你的用户名/my-live2d.git /var/www/my-live2d
```

---

## 5.5 在服务器上装好后端环境

和本地一样，建虚拟环境，装依赖：

```bash
cd /var/www/my-live2d/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

然后创建 `.env` 文件，放后端需要的配置（API Key 这些敏感信息不放代码库，放这里）：

```bash
# 在 backend/ 目录下
nano .env
```

现在先填基础内容，API Key 这章用不上，第 6 章再填：

```
LLM_API_KEY=（第6章填）
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

保存退出（Ctrl+X，Y，回车）。

手动测一下后端能不能起来：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

另开一个终端，运行 `curl http://localhost:8000/api/health`，如果返回 `{"status":"ok"}`，后端没问题。Ctrl+C 停掉，接下来让 systemd 管理它。

---

## 5.6 systemd：让后端在后台一直跑

手动启动的服务，关掉终端就没了，服务器重启也没了。systemd 是 Linux 的服务管理器，可以让程序开机自启、崩溃自重启。

创建服务文件：

```bash
nano /etc/systemd/system/my-live2d.service
```

填入这些内容（把路径里的 `my-live2d` 换成你的实际路径）：

```ini
[Unit]
Description=My Live2D AI Assistant
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/my-live2d/backend
Environment=PATH=/var/www/my-live2d/backend/venv/bin
ExecStart=/var/www/my-live2d/backend/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

注意这里 `--host 127.0.0.1`——后端只监听本机，外部没法直接访问，必须通过 Nginx。这是安全做法。

启用并启动：

```bash
chown -R www-data:www-data /var/www/my-live2d
systemctl daemon-reload
systemctl enable my-live2d
systemctl start my-live2d
systemctl status my-live2d
```

看到 `Active: active (running)`，后端就常驻在后台了。

---

## 5.7 购买域名（可选，但建议有）

没有域名也可以用 IP 地址访问，但 HTTPS 需要域名。域名在各大云厂商都能买，一个普通的 `.com` 一年 50-100 元。

买好之后，在域名商的后台添加一条 A 记录：
- 主机记录：`@`（代表根域名）
- 记录值：你的服务器公网 IP

等几分钟，在命令行里 `ping 你的域名`，如果看到你的服务器 IP，说明解析生效了。

---

## 5.8 Nginx：统一管理进来的请求

Nginx 是一个反向代理服务器。用户的请求先到 Nginx，Nginx 再转给后端。这样做有几个好处：支持 HTTPS、同时服务前端文件和后端 API、后端崩溃时还能显示友好的错误页面。

创建配置文件：

```bash
nano /etc/nginx/sites-available/my-live2d
```

写入：

```nginx
server {
    listen 80;
    server_name 你的域名.com www.你的域名.com;

    location / {
        root /var/www/my-live2d/frontend;
        try_files $uri /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 需要特殊配置（第7章会用到）
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }

    location /audio/ {
        proxy_pass http://127.0.0.1:8000;
    }
}
```

> **你可能会问**：WebSocket 那段配置为什么那么多行？
>
> WebSocket 的握手过程依赖 HTTP Upgrade 机制，需要把 `Upgrade` 和 `Connection` 这两个头原样传给后端。少了这两行，WebSocket 连接会被 Nginx 截断，变成普通 HTTP 请求，连不上。这是 WebSocket 和 Nginx 搭配时的固定写法，记住就行。

启用配置：

```bash
ln -s /etc/nginx/sites-available/my-live2d /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t        # 验证配置语法
systemctl restart nginx
```

现在访问 `http://你的域名`，应该能看到前端页面。

---

## 5.9 配置 HTTPS（免费证书）

HTTPS 是现代 Web 应用的标配。certbot 可以免费申请 Let's Encrypt 证书，而且会自动续期：

```bash
certbot --nginx -d 你的域名.com -d www.你的域名.com
```

按提示操作，输入邮箱，选择"强制 HTTPS 跳转"（选 2）。完成后 certbot 会自动修改 Nginx 配置。

访问 `https://你的域名`，浏览器地址栏里应该有绿色锁标志。

> **试一下**：运行 `certbot renew --dry-run`，如果看到 "Congratulations, all renewals succeeded"，说明自动续期正常，以后不需要手动管证书。

---

## 5.10 最重要的一步：环境感知 URL

现在前端代码里还有 `http://localhost:8000` 这样的硬编码地址。在服务器上，这个地址是错的——服务器没有 localhost:8000 给浏览器访问。

**正确做法**：让前端代码自己判断当前是在本地还是在服务器上，然后选择对应的地址。

在 `frontend/main.js` 最顶部加上这几行（**以后每章都沿用，不要改**）：

```javascript
const IS_LOCAL = ["localhost", "127.0.0.1"].includes(window.location.hostname);

const API_BASE = IS_LOCAL ? "http://localhost:8000" : "";
const WS_PROTOCOL = window.location.protocol === "https:" ? "wss:" : "ws:";
const WS_HOST = IS_LOCAL ? "localhost:8000" : window.location.host;
const WS_BASE = `${WS_PROTOCOL}//${WS_HOST}`;
```

然后把代码里所有的 `"http://localhost:8000"` 换成 `API_BASE`，所有的 `"ws://localhost:8000"` 换成 `WS_BASE`：

```javascript
// 之前
const response = await fetch("http://localhost:8000/api/chat", ...);

// 现在
const response = await fetch(`${API_BASE}/api/chat`, ...);
```

**这几行代码的逻辑**：
- 本地开发：`API_BASE = "http://localhost:8000"`，`WS_BASE = "ws://localhost:8000"`
- 生产服务器：`API_BASE = ""`（空字符串），所以 `/api/chat` 就是同源请求，Nginx 转发给后端；`WS_BASE = "wss://你的域名"`，自动从当前页面 URL 获取

从此以后，你的代码再也不需要因为"要部署到服务器了"而修改任何地址。

---

## 5.11 以后的更新流程

本地改好代码，测试没问题：

```bash
git add .
git commit -m "描述这次改了什么"
git push
```

然后在服务器上：

```bash
cd /var/www/my-live2d
git pull
systemctl restart my-live2d
```

三十秒，更新完成。

---

## 5.12 常用运维命令

查看后端实时日志（出问题时最有用）：
```bash
journalctl -u my-live2d -f
```

重启后端：
```bash
systemctl restart my-live2d
```

检查 Nginx 有没有报错：
```bash
tail -f /var/log/nginx/error.log
```

---

## 本章小结

- 尽早部署：避免最后才移植代码的痛苦
- `IS_LOCAL + API_BASE + WS_BASE` 三个变量，一次配置，永久免移植
- systemd 管理后端服务：开机自启、崩溃自重启
- Nginx 反向代理：WebSocket 需要 `Upgrade` 和 `Connection` 头
- certbot 免费 HTTPS，自动续期
- 更新流程：`git push` → 服务器 `git pull + systemctl restart`

---

→ 下一章：[第 6 章：接入大模型 API](06-接入大模型API.md)
