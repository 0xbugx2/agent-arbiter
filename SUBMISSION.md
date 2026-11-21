# SUBMISSION.md — 提交清单（需要你本人完成的步骤）

> 说明：Muse 只在本地准备了这个代码包，**没有**发布、推送或提交任何东西。
> 下面每一步都由你本人操作。整个过程不需要钱包签名、不需要花钱
> （StudioNet 是 gasless 的；Bradbury 测试网部署也只用测试币）。

## 第 0 步（建议先做，约 10 分钟）：本地验证

在你的 Mac 上打开终端，进入这个代码包目录，运行：

```bash
pip install genlayer-test genvm-linter
genvm-lint check contracts/agent_arbiter.py   # 必须无报错
pytest tests/direct/ -v                       # 18 个测试应全过
```

如果有报错，先把报错发给 Muse 修，不要带病提交。

## 第 1 步：在 GenLayer Studio 部署并跑通一次（重要证据）

审核员看重真实部署。在 https://studio.genlayer.com ：

1. 新建合约文件，把 `contracts/agent_arbiter.py` 的内容整份粘贴进去，部署。
2. 用 Studio 的两个测试账户走一遍 README 里 "Try it in Studio" 的 6 步
   （建协议 → assess_terms → 开争议 → 回应 → resolve_dispute）。
3. 记下：**合约地址**、**resolve_dispute 的交易链接**。第 3 步要填。

## 第 2 步：建公开 GitHub 仓库

你的 Portal 已绑定的 GitHub 账号是 `0xbug83`，用它建仓：

```bash
# 在代码包目录里
git init && git add . && git commit -m "AgentArbiter: GenLayer dispute adjudication contract"
# 在 github.com 上新建公开仓库 agent-arbiter（不要勾选初始化 README），然后：
git remote add origin https://github.com/0xbug83/agent-arbiter.git
git branch -M main && git push -u origin main
```

检查：仓库是 Public；README 能正常渲染；仓库里没有任何私钥/密钥文件。

## 第 3 步：在 Portal 提交

打开 https://portal.genlayer.foundation/submit-contribution ，选择
**Intelligent Contracts** 分类（每周配额 2 次，本次用 1 次），填写：

- **Title**（直接粘贴）：
  `AgentArbiter — On-chain Dispute Adjudication for AI-Agent Service Agreements`

- **Description**（直接粘贴，把 <> 三处换成第 1 步的真实链接）：

  ```
  AgentArbiter is an Intelligent Contract that settles "did the worker
  deliver?" disputes for AI-agent service agreements — the missing
  adjudication layer for the agent economy.

  A client and a worker record a service agreement in natural language.
  If a dispute opens, both sides submit a statement plus a public
  evidence URL. Validators then independently fetch the evidence pages
  and re-run the adjudication on their own LLMs; the verdict (CLIENT_WINS
  / WORKER_WINS / SPLIT with a basis-point payment split / INCONCLUSIVE)
  is stored only when the committee's decision fields are equivalent
  under the contract's rules: outcome exact-match, worker share
  exact-match (SPLIT shares are canonicalized to the nearest 5% step
  inside the evaluation, so the stored settlement value is the one
  value every validator reproduced), confidence within 20, reasoning
  never compared. A second
  non-deterministic operation, assess_terms, scores how adjudicable an
  agreement's terms are before work starts.

  The design follows the GenLayer docs' production patterns:
  run_nondet_unsafe with custom validators that never trust the leader,
  [EXPECTED]/[EXTERNAL]/[LLM_ERROR] error classification, prompt-injection
  hardening for evidence pages, and float-free deterministic state
  transitions. 18 direct-mode tests (mocked web + LLM) cover the full
  lifecycle, access control, and all four verdict outcomes.

  Repo: <GitHub 仓库链接>
  Deployed contract (StudioNet): <合约地址>
  Example adjudication tx: <交易链接>
  ```

- **Link**：填 GitHub 仓库链接。

## 提交前自查

- [ ] genvm-lint 无报错，direct 测试全过
- [ ] Studio 部署成功，至少跑通一次完整争议流程
- [ ] GitHub 仓库为 Public，README 渲染正常
- [ ] Description 里的三个链接是真实的，不是占位符
- [ ] 本周 Intelligent Contracts 配额还剩 ≥1（每周 2 次）

## 注意

- 提交后由 Stewards 人工审核（整体通过率约 18.5%），按提交顺序审，
  本周窗口是周一 00:00 – 周日 23:59 UTC；被拒可以改完重交。
- 不要把这个合约和「刷分模板」一起交：它是独立完整的项目，
  按 Intelligent Contracts 分类单独提交即可。
