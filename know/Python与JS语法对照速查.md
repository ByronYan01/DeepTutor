# Python 与 JS 语法对照速查

> 前端开发者快速上手 Python 的语法对照表

---

## 三元表达式

```python
# Python
result = A if condition else B

# JS
result = condition ? A : B
```

## 列表推导式

```python
# Python
[x * 2 for x in arr]                  # JS: arr.map(x => x * 2)
[x for x in arr if x > 0]             # JS: arr.filter(x => x > 0)
[x * 2 for x in arr if x > 0]         # JS: arr.filter(x => x > 0).map(x => x * 2)
[s for s in sessions if s["id"] != target_id]  # JS: sessions.filter(s => s.id !== targetId)
```

## 字典推导式

```python
# Python
{k: v for k, v in items}              # JS: Object.fromEntries(items)
```

## 变量声明

```python
# Python — 无需关键字
x = 1
x: int = 1          # 带类型注解（可选）

# JS
let x = 1
const x: number = 1 # TypeScript
```

## 函数定义

```python
# Python
def add(a: int, b: int) -> int:
    return a + b

async def fetch():
    result = await get_data()

# JS
function add(a, b) { return a + b }
const add = (a, b) => a + b

async function fetch() {
    const result = await getData()
}
```

## 字符串

```python
# Python — f-string
f"Hello {name}, age {age}"

# JS — 模板字符串
`Hello ${name}, age ${age}`
```

## 切片

```python
# Python
arr[1:3]       # JS: arr.slice(1, 3)
arr[:5]        # JS: arr.slice(0, 5)
arr[-1]        # JS: arr.at(-1)
s[:100]        # JS: s.slice(0, 100)
```

## 解构

```python
# Python
a, b = (1, 2)             # JS: const [a, b] = [1, 2]
a, *rest = [1, 2, 3]      # JS: const [a, ...rest] = [1, 2, 3]
```

## 字典（对象）操作

```python
# Python
d = {"key": "value"}
d.get("key", "default")    # JS: d.key ?? "default"
d["key"]                   # JS: d.key 或 d["key"]
"key" in d                 # JS: "key" in d

# 合并
{**d1, **d2}               # JS: { ...d1, ...d2 }
```

## 循环

```python
# Python
for item in arr:            # JS: for (const item of arr)
for i, item in enumerate(arr):  # JS: arr.forEach((item, i) => ...)
for key, val in d.items():  # JS: Object.entries(d).forEach(([key, val]) => ...)

# async 循环
async for chunk in stream:  # JS: for await (const chunk of stream)
```

## 类

```python
# Python
class Dog(Animal):          # JS: class Dog extends Animal
    def __init__(self):     #     constructor()
        super().__init__()  #         super()
        self.name = "Rex"   #         this.name = "Rex"

    def bark(self):         #     bark()
        print(self.name)    #         console.log(this.name)
```

注意：Python 方法第一个参数必须是 `self`（等同 JS 的 `this`），但调用时不用传。

## 异常处理

```python
# Python
try:
    do_something()
except Exception as e:      # JS: catch (e)
    print(e)
finally:
    cleanup()
```

## None / null

```python
# Python
x is None                   # JS: x === null
x is not None               # JS: x !== null
```

## 类型判断

```python
# Python
isinstance(x, str)          # JS: typeof x === "string"
isinstance(x, (int, float)) # JS: typeof x === "number"
type(x).__name__            # JS: typeof x
```

## 导入

```python
# Python
from module import func             # JS: import { func } from "module"
from module import func as alias    # JS: import { func as alias } from "module"
import module                       # JS: import * as module from "module"
```

## 生成器 / yield

```python
# Python
def gen():
    yield 1
    yield 2

async def async_gen():
    yield 1

# JS
function* gen() {
    yield 1
    yield 2
}

async function* asyncGen() {
    yield 1
}
```

## 常用内置函数

```python
len(arr)          # JS: arr.length
print(x)          # JS: console.log(x)
range(5)          # JS: Array.from({length: 5}, (_, i) => i)
str(x)            # JS: String(x)
int(x)            # JS: parseInt(x)
float(x)          # JS: parseFloat(x)
isinstance(x, T)  # JS: x instanceof T
```
