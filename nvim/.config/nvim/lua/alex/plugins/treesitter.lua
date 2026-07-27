return {
    {
        "nvim-treesitter/nvim-treesitter",
        branch = "main",
        lazy = false, -- required: `main` must load at startup to register parsers/highlighting
        build = ":TSUpdate",
        config = function()
            require("nvim-treesitter").install({
                "c", "lua", "vim", "vimdoc", "query", "javascript", "html", "angular",
                "bash", "c_sharp", "cmake", "cpp", "css", "csv", "diff", "dockerfile",
                "dot", "elixir", "gitcommit", "gitignore", "go", "gomod", "gosum",
                "gowork", "graphql", "hcl", "http", "java", "kotlin", "json", "llvm",
                "make", "markdown", "markdown_inline", "objc", "perl", "php", "python",
                "regex", "ruby", "rust", "scss", "sql", "ssh_config", "strace", "swift",
                "templ", "toml", "tsx", "typescript", "terraform", "vue", "xml", "yaml",
                "zig",
            })

            -- `nomad` files use HCL syntax; give them their own filetype and
            -- point treesitter at the hcl parser for highlighting.
            vim.filetype.add({ extension = { nomad = "nomad" } })
            vim.treesitter.language.register("hcl", "nomad")

            -- The `main` branch drops the highlight module; start highlighting per
            -- buffer whenever an installed parser exists for its filetype.
            local function ts_start(buf, ft)
                local lang = vim.treesitter.language.get_lang(ft) or ft
                if not vim.treesitter.language.add(lang) then return end
                vim.treesitter.start(buf, lang)
            end

            vim.api.nvim_create_autocmd("FileType", {
                group = vim.api.nvim_create_augroup("alex_treesitter_start", {}),
                callback = function(args) ts_start(args.buf, args.match) end,
            })

            -- Cover buffers already loaded before this autocmd was registered.
            for _, buf in ipairs(vim.api.nvim_list_bufs()) do
                if vim.api.nvim_buf_is_loaded(buf) then
                    ts_start(buf, vim.bo[buf].filetype)
                end
            end
        end,
    },
}
