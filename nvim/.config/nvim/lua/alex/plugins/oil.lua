return {
    {
        'stevearc/oil.nvim',
        dependencies = { "nvim-tree/nvim-web-devicons" }, -- use if prefer nvim-web-devicons
        config = function()
            require('oil').setup {
                deault_file_explorer = true,
                view_options = {
                    show_hidden = true,
                }
            }
            vim.keymap.set("n", "-", "<CMD>Oil<CR>", { desc = "Open parent directory" })
        end,
    }
}
