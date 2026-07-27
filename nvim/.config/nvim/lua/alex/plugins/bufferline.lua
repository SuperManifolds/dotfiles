return {
    {
        'akinsho/bufferline.nvim',
        version = "*",
        event = "VeryLazy",
        dependencies = { 'nvim-tree/nvim-web-devicons' },
        opts = {
            options = {
                numbers = "ordinal",             -- match the <A-1>..<A-9> goto positions
                diagnostics = "nvim_lsp",        -- show LSP diagnostics on buffers
                always_show_bufferline = false,  -- auto-hide when only one buffer is open
                show_buffer_close_icons = true,
                show_close_icon = false,
            },
        },
    }
}
