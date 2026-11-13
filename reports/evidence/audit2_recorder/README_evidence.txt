RunA cmd: .venv/bin/python recorder.py (clean clone /tmp/wtr_qa_clone, fresh venv)
RunB cmd: same
RunC cmd: same after editing demonstrate() only: "for i in range(2):" -> "for i in (0, 2):"
cmp steps_runA steps_runB: BYTE-IDENTICAL
cmp skill_runA skill_runB: BYTE-IDENTICAL
cmp skill_runA committed-skill-at-HEAD: IDENTICAL
cmp steps_runA committed-steps-at-HEAD: IDENTICAL
RunC diff: steps.json changed (add-to-cart bike-light -> bolt-t-shirt, item titles, subtotal), skill changed (Locator + Fallback lines, total $19.42 -> $25.90)
