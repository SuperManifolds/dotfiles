return {
    {
        'MeanderingProgrammer/markdown.nvim',
        name = 'render-markdown',              -- Only needed if you have another plugin named markdown.nvim
        dependencies = {
            'nvim-treesitter/nvim-treesitter', -- Mandatory
            'nvim-tree/nvim-web-devicons',     -- Optional but recommended
        },
        config = function()
            require('render-markdown').setup({})

            -- Set up text wrapping for markdown files only
            vim.api.nvim_create_autocmd("FileType", {
                pattern = "markdown",
                callback = function()
                    vim.opt_local.wrap = true        -- Enable text wrapping
                    vim.opt_local.linebreak = true   -- Wrap at word boundaries
                    vim.opt_local.breakindent = true -- Preserve indentation in wrapped text
                    vim.opt_local.conceallevel = 2   -- Hide markup for bold/italic
                    vim.opt_local.textwidth = 0      -- Disable hard wrapping
                    vim.opt_local.wrapmargin = 0     -- Disable wrap margin
                end,
            })
        end,
    }
}
