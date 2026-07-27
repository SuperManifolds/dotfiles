return {
    "nvim-neotest/neotest",
    dependencies = {
        "lawrence-laz/neotest-zig",
        "nvim-lua/plenary.nvim",
        "nvim-treesitter/nvim-treesitter",
        "nvim-neotest/neotest-go",
        "rouge8/neotest-rust",
    },
    config = function()
        require("neotest").setup({
            adapters = {
                -- Registration
                require("neotest-go"),
                require("neotest-rust") {
                    args = { "--no-capture" },
                },
                require("neotest-zig")({
                    dap = {
                        adapter = "lldb",
                    }
                }),
            }
        })
    end
}

