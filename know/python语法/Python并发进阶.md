# Python 并发编程进阶指南（面向前端开发者）

> 本文从 Web 前端（JavaScript/Node.js）开发者的视角出发，用 JS 中熟悉的概念来理解 Python 的三种并发模型。

## 1. 核心概念速查表

| Python 技术 | JS 对等物 | 针对问题 | 关键特征 |
| :--- | :--- | :--- | :--- |
| **协程 (asyncio)** | Event Loop + async/await | 网络 I/O 等待 | 单线程切换任务，极低消耗 |
| **多线程 (threading)** | Web Worker（但共享内存） | 磁盘 I/O / 同步阻塞库 | 共享内存，受 GIL 锁限制 |
| **多进程 (multiprocessing)** | Chrome 多标签页 / Node cluster | CPU 计算密集 | 独立资源，真正并行 |

---

## 2. 协程 (Asyncio) = JS 的事件循环

### 原理

Python 的 `asyncio` 和 JS 的事件循环本质上是**同一个东西**：在**一个进程**的**一个线程**里，通过事件循环不断轮询任务。

```
事件循环不断在做同一件事（无限循环）：
  ① 有没有就绪的任务？→ 有 → 执行它，直到它遇到 await（IO等待）
  ② 有没有 IO 完成了？→ 有 → 唤醒对应的任务，放入就绪队列
  ③ 回到 ①
```

### JS 与 Python 对照

| 概念 | JavaScript | Python |
| :--- | :--- | :--- |
| 异步对象 | `Promise` | `Future` / `Task` |
| 执行关键字 | `await` | `await` |
| 并发等待 | `Promise.all([...])` | `asyncio.gather(...)` |
| 底层核心 | Event Loop (libuv) | Event Loop (asyncio) |
| 是否默认启动 | ✅ 天生就有 | ❌ 需手动启动（`asyncio.run()` 或 FastAPI 帮你启动） |

### 比喻：银行柜台（自觉排队模式）

银行只有一个柜员（CPU），100 个客户（100 个用户请求）同时到来：

- **没有协程（纯同步）**：柜员给客户 1 办业务 → 客户 1 等数据库返回（3 秒）→ 柜员傻等 3 秒 → 办完 → 接下来客户 2 ... 100 个客户排完要 300 秒。
- **有协程**：柜员给客户 1 办 → 客户 1 说"我要等数据库"(`await`) → 客户 1 自觉去旁边坐着 → 柜员立刻给客户 2 办 → 客户 2 也在等 API → 也去旁边坐 → ... → 客户 1 的数据库回来了 → 柜员回来继续给客户 1 办。

> [!IMPORTANT]
> **协程不会让"一个人的事情变快"**，而是让柜员不会因为一个人的等待而闲着。对于单个任务内部，`await` 就是在同步等待。并发的好处体现在**多个用户同时请求服务器**时。

### 并发请求 = `Promise.all`

如果你需要同时从多个地方拿数据，可以使用 `asyncio.gather`（等价于 JS 的 `Promise.all`）：

```python
# Python 版 "Promise.all"
db_result, api_result, local_result = await asyncio.gather(
    query_db(query),       # 同时发起
    fetch_api(query),      # 同时发起
    search_local(query)    # 同时发起
)
# 总时间 = max(各请求时间)，而不是相加
```

```javascript
// JS 等价写法
const [dbResult, apiResult, localResult] = await Promise.all([
    queryDb(query),
    fetchApi(query),
    searchLocal(query)
]);
```

### 项目中的实际应用

DeepTutor 使用 FastAPI 作为 Web 框架。FastAPI 本身就是基于 asyncio 事件循环运行的。当用户 A 在等待 Embedding API 返回向量时，事件循环会去处理用户 B 发来的新消息。

---

## 3. 多线程 (Threading) = 增强版 Web Worker

### 为什么 Python 需要多线程，而 JS 不太需要？

**JS 世界**：几乎所有库都是异步的（`fetch`、数据库驱动全部返回 Promise），你很少遇到"一个函数调了就卡住整个页面"的情况。

**Python 世界**：大量老牌库是**同步的**（PyMuPDF、scikit-learn 等）。它们一旦开始执行，就像一个 `while(true)` 死循环一样霸占着主线程。多线程的存在就是为了**把这些"霸道"的同步库丢到后台线程去跑**。

### JS 与 Python 对照

| | JS Web Worker | Python 多线程 |
| :--- | :--- | :--- |
| 内存是否共享 | ❌ 不共享，必须用 `postMessage` 传数据 | ✅ **共享**，所有线程直接读写同一个变量 |
| 能否操作主逻辑 | ❌ 不能操作 DOM | ✅ 能直接访问主线程的所有数据 |
| 真正并行计算 | ✅ 真并行 | ❌ 受 GIL 限制，CPU 计算不能真并行 |

### GIL（全局解释器锁）是什么？

Python（CPython 解释器）的一个设计：**在一个进程内，同一时刻只允许一个线程执行 Python 字节码**。
- 当线程在进行 **I/O 操作**（读写文件、网络请求）时，它会**主动释放 GIL 锁**，让其他线程有机会运行。
- 所以多线程对于 I/O 密集型任务依然有效，对 CPU 密集型任务则无效。

### 比喻：银行柜台（前台经理查岗模式）

柜员依然只有一个，但银行设了个"前台经理"（Python 解释器）。他拿着秒表，规定：每个人只能在窗口站一小段时间。
- 即使客户 A 在窗口解析一个超大的 PDF，时间一到，经理吹哨："时间到！A 你去后面排着，B 你上！"
- 尽管 A 不乐意，他也被**强行**换下（这叫"抢占式调度"）。

### 项目中的实际应用

在 `llamaindex.py` 中，LlamaIndex 的索引构建函数是同步阻塞的。如果直接在 asyncio 事件循环中调用，会导致整个服务器卡死。所以用 `run_in_executor` 把它丢到后台线程：

```python
# Python 的 run_in_executor ≈ JS 的 new Worker()，但更方便
loop = asyncio.get_event_loop()
index = await loop.run_in_executor(
    None,  # 使用默认线程池
    lambda: VectorStoreIndex.from_documents(documents)  # 在后台线程跑
)
# 后台线程跑完了，主线程拿到结果，继续处理
```

---

## 4. 多进程 (Multiprocessing) = Chrome 多标签页

### 原理

开启**多个独立的进程**，每个进程有自己完整的 Python 解释器和 GIL 锁，可以在不同的 CPU 核心上**真正同时计算**。

### JS 与 Python 对照

| | Chrome 多标签页 / Node cluster | Python 多进程 |
| :--- | :--- | :--- |
| 内存 | 每个标签页/进程有独立的内存 | 每个进程有独立的内存和解释器 |
| 崩溃隔离 | 一个标签页崩了，其他没事 | 一个子进程挂了，主进程没事 |
| 数据通信 | 不能直接访问对方变量 | 需要通过"管道"传数据 |
| CPU 利用 | 可以跑在不同的 CPU 核心上 | ✅ 真正的物理并行 |

### 比喻：银行开分店

总行发现一家银行排队太长，直接在隔壁又开了 3 家一模一样的分店。每个分店都有自己完整的窗口、柜员和经理，4 个客户可以**真正同时**办业务。代价是要付 4 份房租（4 倍内存消耗）。

### 前端开发中你已经接触过的"多进程"思想

1. `npm run build` 时，Webpack/Vite 用多个 worker 进程并行编译不同的文件。
2. Node.js 的 `cluster` 模块：开 4 个 Node 进程监听同一个端口，分摊流量。

### 代码示例

```python
from concurrent.futures import ProcessPoolExecutor

# 开 4 个子进程，真正同时计算
with ProcessPoolExecutor(max_workers=4) as pool:
    results = list(pool.map(heavy_computation, datasets))
```

> [!NOTE]
> DeepTutor 项目目前没有使用多进程，因为瓶颈在**等 API 返回**（等 LLM 生成、等 Embedding 接口），而不是 CPU 计算。用协程 + 线程池已经完全够用。

---

## 5. 线程调度 vs 协程调度

虽然多线程（GIL 下）和协程看起来都是"轮流干活"，但它们的调度方式完全不同：

| | 协程（协作式） | 多线程（抢占式） |
| :--- | :--- | :--- |
| **谁说了算** | **代码自己**，只有写了 `await` 才让出 | **Python 解释器/操作系统**，强制切换 |
| **风险** | 如果没有 `await` 的死循环，整个程序卡死 | "强行换人"可能导致数据竞争，需要加锁 |
| **效率** | 极高，没有上下文切换开销 | 较低，线程切换有额外成本 |
| **适用** | 所有库都支持 async 的场景 | 老库不支持 async，需要后台执行 |

---

## 6. 决策黄金法则

> [!TIP]
> - 任务跑的时候 **CPU 占用低**，大部分在等网络/API → 用 **协程**
> - 任务调用的库**不支持 async** → 用 **线程池**（`run_in_executor`）丢到后台
> - 任务跑的时候 **CPU 飙满 100%** → 用 **多进程**
