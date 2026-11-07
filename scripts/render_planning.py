"""Render task/acceptance Markdown from the maintained JSON sources."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def render():
    tasks=json.loads((ROOT/'planning/backlog.json').read_text(encoding='utf-8'))['tasks']
    cases=json.loads((ROOT/'planning/acceptance.json').read_text(encoding='utf-8'))['cases']
    rows=['# 开发任务清单','', '> 本文件由 `planning/backlog.json` 生成；编辑JSON后运行 `python scripts/render_planning.py`。',
          '', '当前版本扩展0.10.0/服务0.10.0/安装器0.8.1。新增任务in_progress表示代码/构造测试已交付、真实环境仍待验收；done需要对应证据。', '',
          '| ID | 优先级 | 状态 | 任务 | 依赖 |','|---|---|---|---|---|']
    for t in tasks: rows.append(f"| {t['id']} | {t['priority']} | {t['status']} | {t['title']} | {', '.join(t['depends_on']) or '—'} |")
    rows+=['','## 逐项交付与验收','']
    for t in tasks:
        rows += [f"### {t['id']} · {t['title']}", '', f"优先级：{t['priority']}；状态：{t['status']}；依赖：{', '.join(t['depends_on']) or '无'}。", '',
                 '交付物：'+t['deliverable']+'。', '', '验收：'+', '.join(t['acceptance'])+'。', '', '约束：'+t['notes']+'。','']
    a=['# 验收标准与可操作检查','', '> 本文件由 `planning/acceptance.json` 生成。下表是验收条件，不把未运行项目标为通过。', '',
       '`fixture_covered`＝有构造测试；`target_pending`＝真实环境仍待测；`open`＝待实现；`repo_verified`＝本次工程层检查，执行结果见 `../qa/BASELINE_TEST_REPORT.md`。', '',
       '| ID | 场景 | 类别 | 状态 |','|---|---|---|---|']
    for c in cases: a.append(f"| {c['id']} | {c['title']} | {c['kind']} | {c['status']} |")
    a+=['','## 具体步骤','']
    for c in cases:
        a += [f"### {c['id']} · {c['title']}",'','前置：'+c['preconditions']+'。','','操作：'+c['steps']+'。','','预期：'+c['expected']+'。','','当前状态：`'+c['status']+'`。','']
    return {'planning/BACKLOG.md':'\n'.join(rows).strip()+'\n','docs/ACCEPTANCE.md':'\n'.join(a).strip()+'\n'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');args=p.parse_args()
    failed=False
    for name,text in render().items():
        path=ROOT/name
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8')!=text:
                print('[STALE]',name);failed=True
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8');print('[WROTE]',name)
    return 1 if failed else 0
if __name__=='__main__': raise SystemExit(main())
