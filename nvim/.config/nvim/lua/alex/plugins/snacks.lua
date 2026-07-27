return {
    {
        "folke/snacks.nvim",
        priority = 1000,
        lazy = false,
        opts = {
            -- New value (no plugin replaced)
            bigfile = { enabled = true },   -- disable heavy features on huge files
            quickfile = { enabled = true }, -- render the file before plugins load
            input = { enabled = true },     -- better vim.ui.input

            -- Consolidations (replace standalone plugins)
            notifier = { enabled = true },                  -- replaces nvim-notify
            indent = { enabled = true, indent = { char = "▏" } }, -- replaces indent-blankline
            words = { enabled = true },                     -- replaces stcursorword (LSP-reference based)
            picker = { enabled = true },                    -- replaces telescope
            scope = { enabled = true },
            bufdelete = { enabled = true },                 -- layout-preserving buffer close (<A-w>)
        },
        keys = {
            { "<leader>ff", function() Snacks.picker.files() end,   desc = "Find files" },
            { "<leader>fg", function() Snacks.picker.grep() end,    desc = "Live grep" },
            { "<leader>fb", function() Snacks.picker.buffers() end, desc = "Buffers" },
            { "<leader>fh", function() Snacks.picker.help() end,    desc = "Help tags" },
        },
    },
}
