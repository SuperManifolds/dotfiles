return {
    {
        'MeanderingProgrammer/markdown.nvim',
        name = 'render-markdown',              -- Only needed if you have another plugin named markdown.nvim
        ft = { 'markdown' },
        dependencies = {
            'nvim-treesitter/nvim-treesitter', -- Mandatory
            'nvim-tree/nvim-web-devicons',     -- Optional but recommended
        },
        config = function()
            require('render-markdown').setup({})

            -- Text wrapping for markdown files only.
            local md_wrap = function()
                vim.opt_local.wrap = true        -- Enable text wrapping
                vim.opt_local.linebreak = true   -- Wrap at word boundaries
                vim.opt_local.breakindent = true -- Preserve indentation in wrapped text
                vim.opt_local.conceallevel = 2   -- Hide markup for bold/italic
                vim.opt_local.textwidth = 0      -- Disable hard wrapping
                vim.opt_local.wrapmargin = 0     -- Disable wrap margin
            end
            vim.api.nvim_create_autocmd("FileType", { pattern = "markdown", callback = md_wrap })
            -- Apply to the buffer that triggered lazy-loading (its FileType already fired).
            if vim.bo.filetype == "markdown" then md_wrap() end
        end,
    }
}
