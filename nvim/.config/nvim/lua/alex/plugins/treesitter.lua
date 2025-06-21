return { {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    config = function()
        local configs = require("nvim-treesitter.configs")

        configs.setup({
            ensure_installed = {
                "c",
                "lua",
                "vim",
                "vimdoc",
                "query",
                "javascript",
                "html",
                "angular",
                "bash",
                "c_sharp",
                "cmake",
                "cpp",
                "css",
                "csv",
                "diff",
                "dockerfile",
                "dot",
                "elixir",
                "gitcommit",
                "gitignore",
                "go",
                "gomod",
                "gosum",
                "gowork",
                "graphql",
                "hcl",
                "http",
                "java",
                "kotlin",
                "json",
                "llvm",
                "make",
                "markdown",
                "markdown_inline",
                "objc",
                "perl",
                "php",
                "python",
                "regex",
                "ruby",
                "rust",
                "scss",
                "sql",
                "ssh_config",
                "strace",
                "swift",
                "toml",
                "tsx",
                "typescript",
                "terraform",
                "vue",
                "xml",
                "yaml",
                "zig"
            },
        })

        vim.treesitter.language.register('hcl', 'nomad')
        vim.filetype.add({ extensions = { nomad = "hcl" } })
    end
} }
