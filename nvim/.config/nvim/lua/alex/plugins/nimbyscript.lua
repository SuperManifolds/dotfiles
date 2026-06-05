return {
    {
        dir = '/Users/alex/github.com/supermanifolds/nimby_lsp/editors/neovim',
        name = 'nimbyscript',
        lazy = false, -- Force load immediately
        config = function()
            require('nimbyscript').setup({
                cmd = '/Users/alex/github.com/supermanifolds/nimby_lsp/target/release/nimbyscript-lsp',
            })
        end,
    }
}
