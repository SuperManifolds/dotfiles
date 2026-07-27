-- Error collector for scripts/verify.sh.
-- Run after a file is open; pumps the loop so LSP servers attach and validate
-- their config, then writes a structured report to $VERIFY_OUT. Distinguishes
-- real config/plugin errors from benign single-file / environment server notes.

local out_path = os.getenv("VERIFY_OUT") or "/tmp/nvim-verify.out"
local wait_ms = tonumber(os.getenv("VERIFY_WAIT") or "10000")

local buf = vim.api.nvim_get_current_buf()
local ft = vim.bo[buf].filetype

-- Messages that are expected when linting a lone fixture file outside a real
-- project, or server-environment notices unrelated to the nvim config.
local BENIGN = {
    "no database connection",
    "single file",
    "opening a directory",
    "ignoreSingleFileWarning",
    "no go files to analyze",
    "context loading failed",
    "tbl_flatten",
    "checkhealth vim%.deprecated",
    "rootmarkers",
}
local function is_benign(msg)
    msg = msg:lower()
    for _, p in ipairs(BENIGN) do
        if msg:find(p:lower()) then return true end
    end
    return false
end

vim.wait(wait_ms, function() return false end, 100)

local report, errors, notes = {}, 0, 0
local function add(l) report[#report + 1] = l end
local function record(tag, msg)
    msg = tostring(msg):gsub("%s+", " ")
    if is_benign(msg) then
        notes = notes + 1
        add("  NOTE " .. tag .. " " .. msg)
    else
        errors = errors + 1
        add("  ERR  " .. tag .. " " .. msg)
    end
end

add("FILE=" .. vim.api.nvim_buf_get_name(buf))
add("FILETYPE=" .. ft)

local ok_hl, active = pcall(function() return vim.treesitter.highlighter.active[buf] ~= nil end)
add("TS_HIGHLIGHT_ACTIVE=" .. tostring(ok_hl and active))

local names = {}
for _, c in ipairs(vim.lsp.get_clients({ bufnr = buf })) do names[#names + 1] = c.name end
add("LSP_CLIENTS=" .. (#names > 0 and table.concat(names, ",") or "(none)"))

-- lazy plugin load/config/build errors (always real)
local ok_lazy, cfg = pcall(require, "lazy.core.config")
if ok_lazy then
    for name, p in pairs(cfg.plugins) do
        if p._ and p._.error then record("[lazy:" .. name .. "]", p._.error) end
    end
end

-- notifier history at warn+ (LSP window/showMessage routes through here)
pcall(function()
    local hist = Snacks.notifier.get_history({ filter = function(n)
        return n.level == "warn" or n.level == "error"
    end })
    for _, n in ipairs(hist) do record("[notify:" .. tostring(n.level) .. "]", n.msg) end
end)

-- :messages scan for error-shaped lines not already surfaced above
local ok_msg, res = pcall(vim.api.nvim_exec2, "messages", { output = true })
if ok_msg and res.output then
    for line in (res.output .. "\n"):gmatch("(.-)\n") do
        if line:match("[Ee]rror") or line:match("E%d%d+:") or line:match("attempt to")
            or line:match("invalid config") or line:match("Failed to") then
            record("[msg]", line)
        end
    end
end

add("ERRORS=" .. errors)
add("NOTES=" .. notes)
add("VERDICT=" .. (errors == 0 and "CLEAN" or ("ERRORS(" .. errors .. ")")))

local f = assert(io.open(out_path, "w"))
f:write(table.concat(report, "\n") .. "\n")
f:close()
