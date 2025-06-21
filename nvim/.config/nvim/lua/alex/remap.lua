vim.g.mapleader = " "
vim.keymap.set('n', '<leader>u', vim.cmd.UndotreeToggle, { desc = "Toggle undotree" })
vim.keymap.set('n', '<leader>git', vim.cmd.Git, { desc = "Open Git" })

vim.keymap.set("v", "J", ":m '>+1<CR>gv=gv")
vim.keymap.set("v", "K", ":m '<-2<CR>gv=gv")

vim.keymap.set("n", "<C-d>", "<C-d>zz", { desc = "Scroll down half page" })
vim.keymap.set("n", "<C-u>", "<C-u>zz", { desc = "Scroll up half page" })
vim.keymap.set("n", "n", "nzzzv", { desc = "Move to next search item" })
vim.keymap.set("n", "N", "Nzzzv", { desc = "Move to previous search item" })

vim.keymap.set("n", "<leader>y", '"+y', { desc = "Copy to clipboard" })
vim.keymap.set("v", "<leader>y", '"+y', { desc = "Copy to clipboard" })
vim.keymap.set("n", "<leader>Y", "\"+Y", { desc = "Copy to clipboard" })

vim.keymap.set("n", "<leader>f", function()
    vim.lsp.buf.format()
end, { desc = "Format code" })


local map = vim.api.nvim_set_keymap
local opts = { noremap = true, silent = true }
local function with_desc(desc)
    return vim.tbl_extend("force", opts, { desc = desc })
end

map('n', 's', '<c-w>', opts)
vim.api.nvim_set_keymap('t', '<Esc>', '<C-\\><C-n>', { noremap = true, silent = true })

-- Move to previous/next
map('n', '<A-,>', '<Cmd>BufferPrevious<CR>', with_desc("Move to previous buffer"))
map('n', '<A-.>', '<Cmd>BufferNext<CR>', with_desc("Move to next buffer"))
-- Re-order to previous/next
map('n', '<A-<>', '<Cmd>BufferMovePrevious<CR>', with_desc("Re-order to previous buffer"))
map('n', '<A->>', '<Cmd>BufferMoveNext<CR>', with_desc("Re-order to next buffer"))
-- Goto buffer in position...
map('n', '<A-1>', '<Cmd>BufferGoto 1<CR>', with_desc("Goto buffer in position 1"))
map('n', '<A-2>', '<Cmd>BufferGoto 2<CR>', with_desc("Goto buffer in position 2"))
map('n', '<A-3>', '<Cmd>BufferGoto 3<CR>', with_desc("Goto buffer in position 3"))
map('n', '<A-4>', '<Cmd>BufferGoto 4<CR>', with_desc("Goto buffer in position 4"))
map('n', '<A-5>', '<Cmd>BufferGoto 5<CR>', with_desc("Goto buffer in position 5"))
map('n', '<A-6>', '<Cmd>BufferGoto 6<CR>', with_desc("Goto buffer in position 6"))
map('n', '<A-7>', '<Cmd>BufferGoto 7<CR>', with_desc("Goto buffer in position 7"))
map('n', '<A-8>', '<Cmd>BufferGoto 8<CR>', with_desc("Goto buffer in position 8"))
map('n', '<A-9>', '<Cmd>BufferGoto 9<CR>', with_desc("Goto buffer in position 9"))
map('n', '<A-0>', '<Cmd>BufferLast<CR>', with_desc("Goto last buffer"))
-- Pin/unpin buffer
map('n', '<A-p>', '<Cmd>BufferPin<CR>', with_desc("Pin/unpin buffer"))
-- Close buffer
map('n', '<A-w>', '<Cmd>BufferClose<CR>', with_desc("Close buffer"))
-- Wipeout buffer
--                 :BufferWipeout
-- Close commands
--                 :BufferCloseAllButCurrent
--                 :BufferCloseAllButPinned
--                 :BufferCloseAllButCurrentOrPinned
--                 :BufferCloseBuffersLeft
--                 :BufferCloseBuffersRight
-- Magic buffer-picking mode
map('n', '<C-p>', '<Cmd>BufferPick<CR>', with_desc("Magic buffer-picking mode"))
-- Sort automatically by...
map('n', '<Space>bb', '<Cmd>BufferOrderByBufferNumber<CR>', with_desc("Sort automatically by buffer number"))
map('n', '<Space>bd', '<Cmd>BufferOrderByDirectory<CR>', with_desc("Sort automatically by directory"))
map('n', '<Space>bl', '<Cmd>BufferOrderByLanguage<CR>', with_desc("Sort automatically by language"))
map('n', '<Space>bw', '<Cmd>BufferOrderByWindowNumber<CR>', with_desc("Sort automatically by window number"))
vim.keymap.set('n', '<leader>S', '<cmd>lua require("spectre").toggle()<CR>', {
    desc = "Toggle Spectre"
})
vim.keymap.set('n', '<leader>sw', '<cmd>lua require("spectre").open_visual({select_word=true})<CR>', {
    desc = "Search current word"
})
vim.keymap.set('v', '<leader>sw', '<esc><cmd>lua require("spectre").open_visual()<CR>', {
    desc = "Search current word"
})
vim.keymap.set('n', '<leader>sp', '<cmd>lua require("spectre").open_file_search({select_word=true})<CR>', {
    desc = "Search on current file"
})

vim.keymap.set("n", "<leader>xx", function() require("trouble").toggle() end, { desc = "Toggle trouble" })
vim.keymap.set("n", "<leader>xw", function() require("trouble").toggle("workspace_diagnostics") end,
    { desc = "Toggle workspace diagnostics" })
vim.keymap.set("n", "<leader>xd", function() require("trouble").toggle("document_diagnostics") end,
    { desc = "Toggle document diagnostics" })
vim.keymap.set("n", "<leader>xq", function() require("trouble").toggle("quickfix") end, { desc = "Toggle quickfix" })
vim.keymap.set("n", "<leader>xl", function() require("trouble").toggle("loclist") end, { desc = "Toggle loclist" })
vim.keymap.set("n", "gR", function() require("trouble").toggle("lsp_references") end, { desc = "Toggle lsp references" })
vim.keymap.set('n', '<leader>x]', function()
    require('trouble').next({ skip_groups = true, jump = true })
end, { desc = "Next trouble" })
vim.keymap.set('n', '<leader>x[', function()
    require('trouble').previous({ skip_groups = true, jump = true })
end, { desc = "Previous trouble" })

vim.keymap.set("i", "<Tab>", function()
    if require("cmp").visible() then
        require("cmp").confirm({ select = true })
    else
        vim.api.nvim_feedkeys(vim.api.nvim_replace_termcodes("<Tab>", true, false, true), "n", false)
    end
end)

vim.keymap.set('n', 'K', '<cmd>lua vim.lsp.buf.hover()<cr>', with_desc("Show hover"))
vim.keymap.set('n', 'gd', '<cmd>lua vim.lsp.buf.definition()<cr>', with_desc("Go to definition"))
vim.keymap.set('n', 'gD', '<cmd>lua vim.lsp.buf.declaration()<cr>', with_desc("Go to declaration"))
vim.keymap.set('n', 'gi', '<cmd>lua vim.lsp.buf.implementation()<cr>', with_desc("Go to implementation"))
vim.keymap.set('n', 'go', '<cmd>lua vim.lsp.buf.type_definition()<cr>', with_desc("Go to type definition"))
vim.keymap.set('n', 'gr', '<cmd>lua vim.lsp.buf.references()<cr>', with_desc("Go to references"))
vim.keymap.set('n', 'gh', '<cmd>lua vim.lsp.buf.signature_help()<cr>', with_desc("Show signature help"))
vim.keymap.set('n', '<F2>', '<cmd>lua vim.lsp.buf.rename()<cr>', with_desc("Rename symbol"))
vim.keymap.set({ 'n', 'x' }, '<F3>', '<cmd>lua vim.lsp.buf.format({async = true})<cr>', with_desc("Format code"))
vim.keymap.set('n', '<F4>', '<cmd>lua vim.lsp.buf.code_action()<cr>', with_desc("Show code actions"))
vim.keymap.set('n', 'e]', '<cmd>lua vim.diagnostic.goto_next()<cr>', with_desc("Go to next diagnostic"))
vim.keymap.set('n', 'e[', '<cmd>lua vim.diagnostic.goto_prev()<cr>', with_desc("Go to previous diagnostic"))

vim.api.nvim_set_keymap("n", "<Leader>doc", ":lua require('neogen').generate()<CR>", with_desc("Generate documentation"))

vim.keymap.set("n", "<leader>gd", function()
    vim.cmd("GoDoc " .. vim.fn.expand("<cword>"))
end, with_desc("Open GoDoc"))
