vim.opt.termguicolors = true
require("alex.remap")
require("alex.lazy")
require("alex.set")

vim.filetype.add({
    extension = {
        templ = "templ",
    },
    filename = {
        ["mod.txt"] = "dosini",
    },
})

vim.api.nvim_create_autocmd("VimEnter", {
    pattern = "*",
    callback = function()
        local current_win = vim.api.nvim_get_current_win() -- Save the current window
        vim.cmd("belowright 10split | terminal")           -- Open terminal in a split
        vim.api.nvim_set_current_win(current_win)          -- Restore the original window
    end,
})

local golang_organize_imports = function(bufnr, isPreflight)
    local client = vim.lsp.get_clients({ bufnr = bufnr, name = "gopls" })[1]
    if not client then return end

    local params = vim.lsp.util.make_range_params(0, client.offset_encoding)
    params.context = { only = { "source.organizeImports" } }

    if isPreflight then
        client:request("textDocument/codeAction", params, function() end, bufnr)
        return
    end

    local result = vim.lsp.buf_request_sync(bufnr, "textDocument/codeAction", params, 3000)
    for _, res in pairs(result or {}) do
        for _, r in pairs(res.result or {}) do
            if r.edit then
                vim.lsp.util.apply_workspace_edit(r.edit, client.offset_encoding)
            elseif r.command then
                client:exec_cmd(r.command, { bufnr = bufnr })
            end
        end
    end
end

vim.api.nvim_create_autocmd("LspAttach", {
    group = vim.api.nvim_create_augroup("LspFormatting", {}),
    callback = function(args)
        local bufnr = args.buf
        local client = vim.lsp.get_client_by_id(args.data.client_id)

        if client.name == "gopls" then
            -- hack: Preflight async request to gopls, which can prevent blocking when save buffer on first time opened
            golang_organize_imports(bufnr, true)

            vim.api.nvim_create_autocmd("BufWritePre", {
                pattern = "*.go",
                group = vim.api.nvim_create_augroup("LspGolangOrganizeImports." .. bufnr, {}),
                callback = function()
                    golang_organize_imports(bufnr)
                end,
            })
        end
    end,
})



vim.api.nvim_create_autocmd("BufEnter", {
    pattern = "*.templ",
    callback = function() vim.cmd("TSBufEnable highlight") end
})

-- Briefly highlight yanked text (native, replaces a plugin/manual autocmd).
vim.api.nvim_create_autocmd("TextYankPost", {
    callback = function() vim.hl.on_yank() end,
})
