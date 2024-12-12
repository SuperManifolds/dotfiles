return {
    {
        'VonHeikemen/lsp-zero.nvim',
        branch = 'v3.x',
        lazy = true,
        config = false,
        init = function()
            -- Disable automatic setup, we are doing it manually
            vim.g.lsp_zero_extend_cmp = 0
            vim.g.lsp_zero_extend_lspconfig = 0
        end,
    },
    {
        'williamboman/mason.nvim',
        lazy = false,
        config = true,
    },

    -- Autocompletion
    {
        'hrsh7th/nvim-cmp',
        event = 'InsertEnter',
        dependencies = {
            { 'L3MON4D3/LuaSnip' },
        },
        config = function()
            -- Here is where you configure the autocompletion settings.
            local lsp_zero = require('lsp-zero')
            lsp_zero.extend_cmp()

            -- And you can configure cmp even more, if you want to.
            local cmp = require('cmp')
            local cmp_action = lsp_zero.cmp_action()

            cmp.setup({
                formatting = lsp_zero.cmp_format(),
                mapping = cmp.mapping.preset.insert({
                    ['<C-u>'] = cmp.mapping.scroll_docs(-4),
                    ['<C-d>'] = cmp.mapping.scroll_docs(4),
                    ['<C-f>'] = cmp_action.luasnip_jump_forward(),
                    ['<C-b>'] = cmp_action.luasnip_jump_backward(),
                })
            })
        end
    },

    -- LSP
    {
        'neovim/nvim-lspconfig',
        cmd = { 'LspInfo', 'LspInstall', 'LspStart' },
        event = { 'BufReadPre', 'BufNewFile' },
        dependencies = {
            { 'hrsh7th/cmp-nvim-lsp' },
            { 'williamboman/mason-lspconfig.nvim' },
        },
        config = function()
            -- This is where all the LSP shenanigans will live
            local lsp_zero = require('lsp-zero')
            lsp_zero.extend_lspconfig()

            local buffer_autoformat = function(bufnr)
                local group = 'lsp_autoformat'
                vim.api.nvim_create_augroup(group, { clear = false })
                vim.api.nvim_clear_autocmds({ group = group, buffer = bufnr })

                vim.api.nvim_create_autocmd('BufWritePre', {
                    buffer = bufnr,
                    group = group,
                    desc = 'LSP format on save',
                    callback = function()
                        -- note: do not enable async formatting
                        vim.lsp.buf.format({ async = false, timeout_ms = 10000 })
                    end,
                })
            end

            vim.api.nvim_create_autocmd('LspAttach', {
                callback = function(event)
                    local id = vim.tbl_get(event, 'data', 'client_id')
                    local client = id and vim.lsp.get_client_by_id(id)
                    if client == nil then
                        return
                    end

                    -- make sure there is at least one client with formatting capabilities
                    if client.supports_method('textDocument/formatting') then
                        buffer_autoformat(event.buf)
                    end
                end
            })

            --- if you want to know more about lsp-zero and mason.nvim
            --- read this: https://github.com/VonHeikemen/lsp-zero.nvim/blob/v3.x/doc/md/guides/integrate-with-mason-nvim.md
            lsp_zero.on_attach(function(client, bufnr)
                -- see :help lsp-zero-keybindings
                -- to learn the available actions
                if client.server_capabilities.inlayHintProvider then
                    vim.g.inlay_hints_visible = true
                    vim.lsp.inlay_hint.enable(true, { bufnr })
                end
                lsp_zero.default_keymaps({ buffer = bufnr })
            end)

            require('lspconfig').clangd.setup({

            })

            vim.api.nvim_create_autocmd('LspAttach', {
                callback = function(args)
                    local client = vim.lsp.get_client_by_id(args.client_id)
                    if not client then return end

                    if client.supports_method('textDocument/formatting') then
                        vim.api.nvim_create_autocmd('BufWritePre', {
                            buffer = args.buf,
                            callback = function()
                                vim.lsp.buf.format({ bufnr = args.buf, id = client.id })
                            end
                        })
                    end
                end,
            })


            require('mason').setup()

            require('mason-lspconfig').setup({
                ensure_installed = {
                    "clangd",
                    "bashls",
                    "cssls",
                    "dockerls",
                    "eslint",
                    "gopls",
                    "golangci_lint_ls",
                    "jsonls",
                    "html",
                    "lua_ls",
                    "sqls",
                    "taplo",
                    "terraformls",
                    "templ",
                    "yamlls",
                    "zls",
                },
                handlers = {
                    lsp_zero.default_setup,
                    gopls = function()
                        require('lspconfig').gopls.setup({
                            settings = {
                                gopls = {
                                    gofumpt = false,
                                    semanticTokens = true,
                                    staticcheck = true,
                                    hints = {
                                        assignVariableTypes = true,
                                        compositeLiteralFields = true,
                                        compositeLiteralTypes = true,
                                        constantValues = true,
                                        functionTypeParameters = true,
                                        parameterNames = true,
                                        rangeVariableTypes = true
                                    },
                                    analyses = {
                                        shadow = true,
                                        unusedwrite = true,
                                        useany = true,
                                        unusedvariable = true,
                                    },
                                }
                            }
                        })
                    end,
                    tsserver = function()
                        -- (Optional) Configure tsserver for neovim
                        require('lspconfig').tsserver.setup({
                            settings = {
                                typescript = {
                                    inlayHints = {
                                        includeInlayParameterNameHints = 'all',
                                        includeInlayParameterNameHintsWhenArgumentMatchesName = false,
                                        includeInlayFunctionParameterTypeHints = true,
                                        includeInlayVariableTypeHints = true,
                                        includeInlayVariableTypeHintsWhenTypeMatchesName = false,
                                        includeInlayPropertyDeclarationTypeHints = true,
                                        includeInlayFunctionLikeReturnTypeHints = true,
                                        includeInlayEnumMemberValueHints = true,
                                    }
                                },
                                javascript = {
                                    inlayHints = {
                                        includeInlayParameterNameHints = 'all',
                                        includeInlayParameterNameHintsWhenArgumentMatchesName = false,
                                        includeInlayFunctionParameterTypeHints = true,
                                        includeInlayVariableTypeHints = true,
                                        includeInlayVariableTypeHintsWhenTypeMatchesName = false,
                                        includeInlayPropertyDeclarationTypeHints = true,
                                        includeInlayFunctionLikeReturnTypeHints = true,
                                        includeInlayEnumMemberValueHints = true,
                                    }
                                }
                            }
                        })
                    end,
                    basedpyright = function()
                        require('lspconfig').pyright.setup({
                            settings = {
                                python = {
                                    analysis = {
                                        typeCheckingMode = "basic",
                                        autoSearchPaths = true,
                                        useLibraryCodeForTypes = true,
                                        diagnosticMode = "workspace",
                                        stubPath = "/usr/lib/python3.9/site-packages"
                                    }
                                }
                            }
                        })
                    end,
                    rust_analyzer = function()
                        require('lspconfig').rust_analyzer.setup({
                            checkOnSave = {
                                command = "clippy"
                            },
                            inlayHints = {
                                bindingModeHints = { enable = true },
                                chainingHints = { enable = true },
                                closingBraceHints = { enable = true },
                                closureCaptureTypeHints = { enable = true },
                                closureReturnTypeHints = { enable = true },
                                discriminantHints = { enable = true },
                                expressionAdjustmentHints = { enable = true },
                                implicitDropsHints = { enable = true },
                                lifetimeElisionHints = { enable = true },
                                parameterHints = { enable = true },
                                rangeExclusionHints = { enable = true },
                                typeHints = { enable = true },
                            },
                            typing = {
                                autoClosingAngleBrackets = { enable = true }
                            }
                        })
                    end,

                    lua_ls = function()
                        require('lspconfig').lua_ls.setup({
                            settings = {
                                Lua = {
                                    diagnostics = {
                                        globals = { 'vim' }
                                    }
                                }
                            }
                        })
                    end
                }
            })
        end
    }
}
