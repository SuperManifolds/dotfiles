## renpy-walkthrough inventory dumper. Copied into game/ by `rpw.py dump` and removed again
## right after the lint run. Inert unless the RPW_OUT environment variable is set.
## Must stay valid under Ren'Py 7 (Python 2) and Ren'Py 8 (Python 3): no f-strings.

init 998 python:
    import os as _rpw_os

    def _rpw_main(out_path):
        import json, io, re, sys

        ast = renpy.ast
        say_limit = 120
        outline_depth = 4
        outline_limit = 250
        outline_hard_limit = 800
        key_kinds = ("python", "jump", "call", "label", "menu", "if", "while", "return")
        card_re = re.compile(r"\b(chapter|episode|day|part|act)\s*[0-9]+", re.I)

        def norm(fn):
            fn = (fn or "").replace("\\", "/")
            if fn.startswith("game/"):
                fn = fn[5:]
            if fn.endswith(".rpyc"):
                fn = fn[:-1]
            return fn

        def text(s, limit=say_limit):
            s = u"%s" % (s,)
            s = s.replace("\n", " ")
            return s if len(s) <= limit else s[:limit] + u"..."

        def var_name(node):
            st = getattr(node, "store", "store") or "store"
            name = node.varname
            return name if st == "store" else st[6:] + "." + name if st.startswith("store.") else name

        def args_text(info):
            """`(a, b=c)` for an ArgumentInfo / ParameterInfo across engine versions, or ''."""
            if info is None:
                return u""
            try:
                parts = []
                for entry in getattr(info, "arguments", None) or []:
                    name, expr = entry[0], entry[1]
                    parts.append(u"%s=%s" % (name, expr) if name else u"%s" % (expr,))
                params = getattr(info, "parameters", None)
                if isinstance(params, dict):
                    params = list(params.values())
                for entry in params or []:
                    if isinstance(entry, tuple):
                        name, default = entry[0], entry[1] if len(entry) > 1 else None
                    else:
                        name, default = getattr(entry, "name", entry), getattr(entry, "default", None)
                    parts.append(u"%s=%s" % (name, default) if default is not None else u"%s" % (name,))
                return u"(%s)" % u", ".join(parts)
            except Exception:
                return u"(...)"

        def sl_lines(node, depth, out):
            """A readable outline of a screen-language node: displayables, keywords, conditions, actions."""
            pad = u"    " * depth
            name = type(node).__name__
            if name == "SLIf":
                for i, (cond, block) in enumerate(node.entries):
                    out.append((None, pad + (u"if %s:" % cond if i == 0 else (u"else:" if cond is None else u"elif %s:" % cond))))
                    sl_lines(block, depth + 1, out)
                return
            if name == "SLFor":
                out.append((None, u"%sfor %s in %s:" % (pad, node.variable, node.expression)))
                depth += 1
            elif name == "SLDefault":
                out.append((None, u"%sdefault %s = %s" % (pad, node.variable, node.expression)))
            elif name == "SLPython":
                out.append((None, u"%s$ %s" % (pad, getattr(node.code, "source", u"").strip())))
            elif name == "SLUse":
                out.append((None, u"%suse %s%s" % (pad, node.target, args_text(getattr(node, "args", None)))))
            elif name in ("SLDisplayable", "SLBlock", "SLScreen"):
                disp = getattr(node, "displayable", None)
                head = getattr(disp, "__name__", u"") if disp is not None else u""
                style = getattr(node, "style", None)
                pos = u" ".join(u"%s" % p for p in getattr(node, "positional", []) or [])
                kws = u" ".join(u"%s %s" % (k, v) for k, v in getattr(node, "keyword", []) or [])
                line = u" ".join(x for x in (head.lstrip("_"), style or u"", pos, kws) if x)
                if line and name != "SLScreen":
                    out.append((None, pad + line))
                    depth += 1
            for child in getattr(node, "children", None) or []:
                sl_lines(child, depth, out)

        def describe(node):
            """Return (kind, short text) for one AST node."""
            if isinstance(node, ast.Say):
                return "say", u"%s: %s" % (node.who or "", text(node.what))
            if isinstance(node, ast.Python):
                return "python", text(node.code.source, 400)
            if isinstance(node, ast.If):
                return "if", u" / ".join(u"else" if c in (None, "True") and i else text(c, 200) for i, (c, _) in enumerate(node.entries))
            if isinstance(node, ast.While):
                return "while", text(node.condition, 200)
            if isinstance(node, ast.Jump):
                return "jump", (u"expression " if node.expression else u"") + text(node.target, 200)
            if isinstance(node, ast.Call):
                return "call", (u"expression " if node.expression else u"") + text(node.label, 200) + args_text(getattr(node, "arguments", None))
            if isinstance(node, ast.Menu):
                return "menu", u" | ".join(text(l, 60) for l, _, _ in node.items)
            if isinstance(node, ast.Label):
                return "label", node.name if isinstance(node.name, str) else u"%s" % (node.name,)
            if isinstance(node, ast.Return):
                return "return", u""
            if isinstance(node, ast.UserStatement):
                return "stmt", text(node.line, 200)
            if type(node).__name__ in ("Define", "Default"):
                return type(node).__name__.lower(), u"%s = %s" % (var_name(node), text(node.code.source, 400))
            if isinstance(node, (ast.Show, ast.Scene, ast.Hide)):
                kind = "hide" if isinstance(node, ast.Hide) else "show"
                return kind, u" ".join(node.imspec[0]) if node.imspec else u""
            return type(node).__name__.lower(), u""

        def children(node):
            """Child blocks of a node, as (tag, block) pairs."""
            if isinstance(node, ast.If):
                first = node.entries[0][0] if node.entries else u""
                tags = []
                for i, (c, b) in enumerate(node.entries):
                    if i == 0:
                        tags.append((u"if %s" % c, b))
                    elif c in (None, "True"):
                        tags.append((u"else (of if %s)" % first, b))
                    else:
                        tags.append((u"elif %s" % c, b))
                return tags
            if isinstance(node, ast.While):
                return [(u"while %s" % node.condition, node.block)]
            if isinstance(node, ast.Menu):
                return [(u"item %s" % text(l, 60), b) for l, _, b in node.items if b is not None]
            if isinstance(node, (ast.Label, ast.Init)) or type(node).__name__ == "Translate":
                return [(u"", getattr(node, "block", None) or [])]
            return []

        def noise(node):
            """Nodes that carry no meaning for analysis: translation wrappers, `with`, `pass`, `call ... from` labels."""
            name = type(node).__name__
            if name in ("EndTranslate", "With", "Pass"):
                return True
            return isinstance(node, ast.Label) and u"%s" % (node.name,) and (u"%s" % (node.name,)).startswith("_call_")

        def outline(block, depth, lines, counts):
            for node in block or []:
                if type(node).__name__ == "Translate":
                    outline(node.block, depth, lines, counts)
                    continue
                if noise(node):
                    continue
                kind, desc = describe(node)
                counts["nodes"] += 1
                if kind == "say":
                    counts["say"] += 1
                if len(lines) < outline_limit or (kind in key_kinds and len(lines) < outline_hard_limit):
                    lines.append([depth, node.linenumber, kind, desc])
                else:
                    counts["cut"] = counts.get("cut", 0) + 1
                if depth < outline_depth:
                    for _tag, sub in children(node):
                        if not isinstance(node, ast.Label):
                            outline(sub, depth + 1, lines, counts)

        def say_count(block):
            n = 0
            for node in block or []:
                if isinstance(node, ast.Say):
                    n += 1
                for _tag, sub in children(node):
                    n += say_count(sub)
            return n

        menus, reads, inputs, callscreens, pymenus, cards, labels, defines, showscreens = [], [], [], [], [], [], [], [], []

        after_limit = 25

        def after_menu(block, k, cont):
            """Outline of what runs right after the menu at block[k], up to the next menu. When the menu ends its
            block, continue in the enclosing blocks (`cont`); a label reached by falling through is included."""
            rest = []
            for siblings, at in [(block, k)] + list(cont):
                for node in (siblings or [])[at + 1:]:
                    if isinstance(node, ast.Menu):
                        break
                    rest.append(node)
                    if isinstance(node, (ast.Label, ast.Jump, ast.Return)):
                        break
                else:
                    if not rest:
                        continue
                break
            lines, counts = [], {"nodes": 0, "say": 0}
            outline(rest, 0, lines, counts)
            return {"say": counts["say"], "outline": lines[:after_limit], "cut": max(0, len(lines) - after_limit)}

        def visit(block, chain, label, cont=()):
            for k, node in enumerate(block or []):
                fn = norm(node.filename)
                if isinstance(node, ast.Label):
                    name = u"%s" % (node.name,)
                    # A label without its own block runs the statements that follow it in the enclosing block.
                    said = say_count(node.block) if node.block else say_count((block or [])[k + 1:])
                    labels.append({"file": fn, "line": node.linenumber, "name": name, "say": said})
                    visit(node.block, [], name, [(block, k)] + list(cont))
                    continue
                if isinstance(node, ast.Menu):
                    items = []
                    item_args = getattr(node, "item_arguments", None) or []
                    for idx, (cap, cond, blk) in enumerate(node.items):
                        iargs = args_text(item_args[idx]) if idx < len(item_args) and item_args[idx] is not None else u""
                        lines, counts = [], {"nodes": 0, "say": 0}
                        if blk is not None:
                            outline(blk, 0, lines, counts)
                        items.append({
                            "index": idx,
                            "caption": cap,
                            "condition": cond,
                            "choice": blk is not None,
                            "line": blk[0].linenumber if blk else node.linenumber,
                            "say": counts["say"],
                            "nodes": counts["nodes"],
                            "cut": counts.get("cut", 0),
                            "outline": lines,
                            "arguments": iargs,
                        })
                        if iargs:
                            reads.append({"file": fn, "line": node.linenumber, "kind": "menu-arg", "code": iargs})
                    menus.append({"file": fn, "line": node.linenumber, "label": label,
                                  "chain": list(chain), "set": node.set, "items": items,
                                  "arguments": args_text(getattr(node, "arguments", None)),
                                  "after": after_menu(block, k, cont)})
                    for cap, cond, blk in node.items:
                        if cond not in (None, "True"):
                            reads.append({"file": fn, "line": node.linenumber, "kind": "menu-if", "code": cond})
                elif isinstance(node, ast.If):
                    for cond, _ in node.entries:
                        if cond not in (None, "True"):
                            reads.append({"file": fn, "line": getattr(cond, "linenumber", None) or node.linenumber, "kind": "if", "code": cond})
                elif isinstance(node, ast.While):
                    reads.append({"file": fn, "line": node.linenumber, "kind": "while", "code": node.condition})
                elif isinstance(node, ast.Python):
                    src = node.code.source
                    reads.append({"file": fn, "line": node.linenumber, "kind": "python", "code": src})
                    if "renpy.input(" in src:
                        inputs.append({"file": fn, "line": node.linenumber, "code": src})
                    if "renpy.call_screen(" in src:
                        callscreens.append({"file": fn, "line": node.linenumber, "code": src})
                    if "renpy.display_menu(" in src:
                        pymenus.append({"file": fn, "line": node.linenumber, "code": src})
                elif type(node).__name__ in ("Define", "Default"):
                    defines.append({"file": fn, "line": node.linenumber, "kind": type(node).__name__.lower(),
                                    "name": var_name(node), "code": node.code.source})
                elif isinstance(node, ast.UserStatement):
                    if node.line.startswith("call screen"):
                        callscreens.append({"file": fn, "line": node.linenumber, "code": node.line})
                    elif node.line.startswith("show screen"):
                        showscreens.append({"file": fn, "line": node.linenumber, "code": node.line})
                elif isinstance(node, ast.Say):
                    what = u"%s" % (node.what,)
                    if card_re.search(what) and len(what) < 80:
                        cards.append({"file": fn, "line": node.linenumber, "label": label, "text": text(what)})
                for tag, sub in children(node):
                    kind, desc = describe(node)
                    # When a child block ends, execution continues after this node (labels fall through too).
                    visit(sub, chain + [[node.linenumber, tag if tag else kind]], label, [(block, k)] + list(cont))

        def pseudo(block, depth, out):
            """Ren'Py-like source lines for a block: (line number or None, text)."""
            pad = u"    " * depth
            for node in block or []:
                ln = node.linenumber
                if noise(node):
                    continue
                if isinstance(node, ast.Label):
                    out.append((ln, u"%slabel %s%s:" % (pad, node.name, args_text(getattr(node, "parameters", None)))))
                    pseudo(node.block, depth + 1, out)
                elif isinstance(node, ast.Return) and depth == 0:
                    continue  # the implicit end-of-file return
                elif type(node).__name__ in ("Define", "Default"):
                    out.append((ln, u"%s%s %s = %s" % (pad, type(node).__name__.lower(), var_name(node), node.code.source.strip())))
                elif type(node).__name__ == "Screen":
                    scr = node.screen
                    out.append((ln, u"%sscreen %s%s:" % (pad, scr.name, args_text(getattr(scr, "parameters", None)))))
                    sl_lines(scr, depth + 1, out)
                elif isinstance(node, ast.If):
                    for i, (cond, blk) in enumerate(node.entries):
                        head = u"if %s:" % cond if i == 0 else (u"else:" if cond == "True" else u"elif %s:" % cond)
                        out.append((ln if i == 0 else None, pad + head))
                        pseudo(blk, depth + 1, out)
                elif isinstance(node, ast.While):
                    out.append((ln, u"%swhile %s:" % (pad, node.condition)))
                    pseudo(node.block, depth + 1, out)
                elif isinstance(node, ast.Menu):
                    out.append((ln, pad + u"menu:"))
                    for cap, cond, blk in node.items:
                        tail = u"" if cond in (None, "True") else u" if %s" % cond
                        if blk is None:
                            out.append((None, u"%s    %s" % (pad, json.dumps(cap, ensure_ascii=False))))
                        else:
                            out.append((None, u"%s    %s%s:" % (pad, json.dumps(cap, ensure_ascii=False), tail)))
                            pseudo(blk, depth + 2, out)
                elif isinstance(node, ast.Say):
                    who = (node.who + u" ") if node.who else u""
                    out.append((ln, u"%s%s%s" % (pad, who, json.dumps(u"%s" % node.what, ensure_ascii=False))))
                elif isinstance(node, ast.Python):
                    src = node.code.source.strip("\n")
                    if "\n" in src:
                        out.append((ln, pad + u"python:"))
                        for l in src.split("\n"):
                            out.append((None, pad + u"    " + l))
                    else:
                        out.append((ln, pad + u"$ " + src))
                elif isinstance(node, ast.Init):
                    out.append((ln, u"%sinit %s:" % (pad, node.priority)))
                    pseudo(node.block, depth + 1, out)
                elif type(node).__name__ == "Translate":
                    pseudo(node.block, depth, out)
                elif type(node).__name__ == "EndTranslate":
                    continue
                else:
                    kind, desc = describe(node)
                    if kind in ("with", "pass"):
                        continue
                    out.append((ln, u"%s%s %s" % (pad, kind, desc)))
            return out

        def write_cfg(path, nodes):
            """The control-flow graph of the game's statements, for path-aware point budgets.
            Node: [file index, line, kind, successors, call target, guards]. Kinds: "n" plain, "p" python, "c" call
            (successor = the statement after the call returns), "r" return, "x" jump or call to a computed label (no
            known target; a computed `call` is "c" with no target). Guards (if/while/menu only) align with the successors: each is a list of
            [condition source, required truth value] that must all hold for that edge."""
            index = dict((id(n), i) for i, n in enumerate(nodes))
            files, file_ix = [], {}

            def ix(node):
                return index.get(id(node), -1) if node is not None else -1

            def first(block, fallback):
                return ix(block[0]) if block else ix(fallback)

            labels = {}
            for n in nodes:
                if isinstance(n, ast.Label) and isinstance(n.name, str):
                    labels[n.name] = ix(n)
            out = []
            for n in nodes:
                fn = norm(n.filename)
                if fn not in file_ix:
                    file_ix[fn] = len(files)
                    files.append(fn)
                kind, succ, target, guards = "n", [], None, None
                if isinstance(n, ast.If):
                    guards, earlier = [], []
                    for c, b in n.entries:
                        succ.append(first(b, n.next))
                        guards.append(earlier + ([] if c in (None, "True") else [[u"%s" % c, True]]))
                        earlier = earlier + ([] if c in (None, "True") else [[u"%s" % c, False]])
                    if not n.entries or n.entries[-1][0] not in (None, "True"):
                        succ.append(ix(n.next))
                        guards.append(earlier)
                elif isinstance(n, ast.While):
                    succ = [first(n.block, n), ix(n.next)]
                    guards = [[[u"%s" % n.condition, True]], [[u"%s" % n.condition, False]]]
                elif isinstance(n, ast.Menu):
                    conds = [u"%s" % c for _l, c, b in n.items if b is not None]
                    succ = [first(b, n.next) for _l, _c, b in n.items if b is not None]
                    guards = [[] if c in ("None", "True") else [[c, True]] for c in conds]
                    # A `set` menu is skipped once every item was picked, and any menu when no condition holds.
                    # (No all()/any(): some games define characters with those names in the store.)
                    if getattr(n, "set", None):
                        succ.append(ix(n.next))
                        guards.append([])
                    elif not [c for c in conds if c in ("None", "True")]:
                        succ.append(ix(n.next))
                        guards.append([[c, False] for c in conds])
                elif isinstance(n, ast.Jump):
                    if n.expression:
                        kind = "x"
                    else:
                        succ = [labels.get(n.target, -1)]
                elif isinstance(n, ast.Call):
                    # A computed target is unknown, but the call still returns to the next statement.
                    kind, target = "c", (None if n.expression else n.label)
                    succ = [ix(n.next)]
                elif isinstance(n, ast.Return):
                    kind = "r"
                elif type(n).__name__ == "Translate":
                    succ = [first(n.block, n.next)]
                elif isinstance(n, ast.Python):
                    kind, succ = "p", [ix(n.next)]
                else:
                    succ = [ix(n.next)]
                row = [file_ix[fn], n.linenumber, kind, [s for s in succ if s >= 0], target]
                if guards is not None:
                    row.append([g for s, g in zip(succ, guards) if s >= 0])
                out.append(row)
            with io.open(path + ".tmp", "w", encoding="utf-8") as f:
                f.write(u"%s" % json.dumps({"files": files, "labels": labels, "nodes": out}, separators=(",", ":")))
            if _rpw_os.path.exists(path):
                _rpw_os.remove(path)
            _rpw_os.rename(path + ".tmp", path)

        roots = {}
        for node in renpy.game.script.namemap.values():
            fn = norm(node.filename)
            if fn.startswith(("renpy/", "common/", "_", "tl/")):
                continue
            roots.setdefault(fn, []).append(node)

        # Top-level statements are those not reachable from any other node's blocks.
        nested = set()
        for nodes in roots.values():
            for node in nodes:
                for _tag, sub in children(node):
                    for child in sub or []:
                        nested.add(id(child))
        pseudo_dir = _rpw_os.environ.get("RPW_PSEUDO")
        for fn in sorted(roots):
            top = sorted((n for n in roots[fn] if id(n) not in nested), key=lambda n: (n.linenumber, isinstance(n, ast.Return)))
            visit(top, [], None)
            if pseudo_dir:
                path = _rpw_os.path.join(pseudo_dir, fn + ".txt")
                if not _rpw_os.path.isdir(_rpw_os.path.dirname(path)):
                    _rpw_os.makedirs(_rpw_os.path.dirname(path))
                with io.open(path, "w", encoding="utf-8") as f:
                    for ln, line in pseudo(top, 0, []):
                        for n, part in enumerate(line.split(u"\n")):  # multi-line defines/python stay prefixed
                            f.write(u"%7s | %s\n" % (ln if ln is not None and n == 0 else u"", part))

        cfg_path = _rpw_os.environ.get("RPW_CFG")
        if cfg_path:
            write_cfg(cfg_path, [n for nodes in roots.values() for n in nodes])

        screens = []
        for (name, variant), scr in renpy.display.screen.screens.items():
            loc = getattr(scr, "location", None)
            screens.append({"name": name, "variant": variant,
                            "file": norm(loc[0]) if loc else None, "line": loc[1] if loc else None})

        flt = renpy.config.say_menu_text_filter
        data = {
            "engine": list(renpy.version_tuple),
            "python": sys.version_info[0],
            "name": renpy.config.name,
            "version": renpy.config.version,
            "save_directory": renpy.config.save_directory,
            "say_menu_text_filter": getattr(flt, "__name__", repr(flt)) if flt else None,
            "menu_include_disabled": bool(renpy.config.menu_include_disabled),
            "menus": sorted(menus, key=lambda m: (m["file"], m["line"])),
            "reads": reads,
            "inputs": inputs,
            "callscreens": callscreens,
            "pymenus": pymenus,
            "cards": cards,
            "labels": labels,
            "defines": defines,
            "showscreens": showscreens,
            "dumper": _rpw_os.environ.get("RPW_DUMPER_HASH"),
            "screens": sorted(screens, key=lambda s: (s["name"], s["variant"] or "")),
        }
        tmp = out_path + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as f:
            f.write(u"%s" % json.dumps(data, indent=1, sort_keys=True))
        if _rpw_os.path.exists(out_path):
            _rpw_os.remove(out_path)
        _rpw_os.rename(tmp, out_path)  # readers never see a half-written dump
        sys.stdout.write("rpw-dump: %d menus written to %s\n" % (len(menus), out_path))

    if _rpw_os.environ.get("RPW_OUT"):
        _rpw_main(_rpw_os.environ["RPW_OUT"])
