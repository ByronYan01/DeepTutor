1. 基础准备：克隆仓库并关联上游
首先克隆开源项目的仓库，并把官方仓库设置为上游（方便后续拉取更新
```bash
# 1. 克隆你Fork后的仓库（如果还没Fork，先在GitHub/Gitee上Fork官方仓库）
git clone https://github.com/你的用户名/目标开源项目.git
cd 目标开源项目

# 2. 添加官方仓库为上游仓库（替换为实际的官方仓库地址）
git remote add upstream https://github.com/官方用户名/目标开源项目.git

# 验证是否添加成功（能看到origin和upstream两个远程仓库）
git remote -v
```

2. 分支管理：创建你的自定义分支
永远不要直接在main/master分支做修改，用专属分支存放你的代码和心得
```bash
# 1. 确保本地main分支是最新的（先拉取官方最新代码）
git checkout main
git pull upstream main  # 从官方上游拉取最新代码
git push origin main    # 同步到你Fork的远程仓库

# 2. 创建并切换到你的自定义分支（比如命名为dev-yl）
git checkout -b dev-yl
```

3. 日常修改：在自定义分支做改动
在dev-yl分支里自由修改代码、添加学习心得文档（比如learning-notes.md）
```bash
# 做修改后，提交你的更改
git add .  # 添加所有修改的文件
git commit -m "添加学习心得：修改了XX功能的注释，理解了YY逻辑"

# 可选：推送到你Fork的远程仓库（备份你的修改）
git push origin dev-yl
```

4. 同步官方更新：拉取并解决冲突
当官方仓库有新更新时，按以下步骤同步并处理冲突
```bash
# 步骤1：切回main分支，拉取官方最新代码
git checkout main
git pull upstream main

# 步骤2：切回你的自定义分支，合并main分支的更新
git checkout dev-yl
git merge main

# 步骤3：如果出现冲突（终端会提示 "Automatic merge failed; fix conflicts and then commit the result"）
# 1) 打开冲突文件，找到标记 <<<<<<< HEAD / ======= / >>>>>>> main 的地方
# 2) 手动编辑保留需要的代码（删除冲突标记）
# 3) 解决完所有冲突后，提交合并结果
git add .
git commit -m "合并官方最新更新，解决XX文件的冲突"

# 可选：推送更新后的自定义分支到远程
git push origin dev-yl
```
