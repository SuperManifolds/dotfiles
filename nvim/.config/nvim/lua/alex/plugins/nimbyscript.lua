-- Local plugin for the in-house nimbyscript LSP. Only load it on a machine
-- where the repo is actually checked out, so this config stays portable across
-- machines (the paths are resolved from $HOME, not hardcoded).
local nimby_dir = vim.fn.expand('~/github.com/supermanifolds/nimby_lsp')

if vim.fn.isdirectory(nimby_dir) == 0 then
    return {}
end

return {
    {
        dir = nimby_dir .. '/editors/neovim',
        name = 'nimbyscript',
        lazy = false, -- Force load immediately
        config = function()
            require('nimbyscript').setup({
                cmd = nimby_dir .. '/target/release/nimbyscript-lsp',
            })
        end,
    }
}
