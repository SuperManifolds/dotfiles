return {
    {
        "kevinhwang91/nvim-ufo",
       dependencies = {
            "kevinhwang91/promise-async",
       },
       event = "BufRead",
       opts = {
            provider_selector = function(bufnr, filetype, buftype)
                return {'treesitter', 'indent'}
            end,
            
       },
       config = function ()
            vim.o.foldcolumn = '1'
            vim.o.foldlevel = 99
            vim.o.foldlevelstart = 99
            vim.o.foldenable = true

            vim.keymap.set('n', 'zR', require('ufo').openAllFolds)
            vim.keymap.set('n', 'zM', require('ufo').closeAllFolds)
            vim.keymap.set('n', 'K', function()
                local winid = require('ufo').peekFoldedLinesUnderCursor(true)
                if not winid then
                    vim.lsp.buf.hover()
                end
            end, {desc = 'LSP: Show hover documentation and folded code'})
            vim.o.fillchars = [[eob: ,fold: ,foldopen:,foldsep: ,foldclose:]]
        end
        }
}
