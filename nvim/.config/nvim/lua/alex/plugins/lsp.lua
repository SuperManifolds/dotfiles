return {
    {
        'williamboman/mason.nvim',
        lazy = false,
        config = true,
    },
    {
        "ray-x/go.nvim",
        dependencies = { -- optional packages
            "ray-x/guihua.lua",
            "neovim/nvim-lspconfig",
            "nvim-treesitter/nvim-treesitter",
        },
        config = function()
        end,
        event = { "CmdlineEnter" },
        ft = { "go", 'gomod' },
        build = ':lua require("go.install").update_all_sync()',
    },

    -- LSP (native vim.lsp, Neovim 0.11+). Completion capabilities come from
    -- blink.cmp; server enablement is handled by mason-lspconfig's
    -- automatic_enable, with per-server settings registered via vim.lsp.config.
    {
        'neovim/nvim-lspconfig',
        cmd = { 'LspInfo', 'LspInstall', 'LspStart' },
        event = { 'BufReadPre', 'BufNewFile' },
        dependencies = {
            { 'williamboman/mason-lspconfig.nvim' },
        },
        config = function()
            -- Filter out "no package metadata" gopls messages
            local original_notify = vim.notify
            vim.notify = function(msg, level, opts)
                if type(msg) == "string" and (msg:find("no package metadata") or msg:find("inotify")) then
                    return
                end
                original_notify(msg, level, opts)
            end

            -- Advertise blink.cmp's completion capabilities to every server.
            -- Falls back to protocol defaults if blink can't load, so LSP
            -- (diagnostics/hover/format) keeps working regardless.
            local ok_blink, blink = pcall(require, 'blink.cmp')
            local capabilities = ok_blink and blink.get_lsp_capabilities()
                or vim.lsp.protocol.make_client_capabilities()
            vim.lsp.config('*', { capabilities = capabilities })

            vim.api.nvim_create_autocmd('LspAttach', {
                callback = function(args)
                    local client = vim.lsp.get_client_by_id(args.client_id)
                    if not client then return end

                    -- Inlay hints where supported.
                    if client.server_capabilities.inlayHintProvider then
                        vim.g.inlay_hints_visible = true
                        vim.lsp.inlay_hint.enable(true, { bufnr = args.buf })
                    end

                    -- Diagnostic float under cursor (parity with lsp-zero's default keymap).
                    vim.keymap.set('n', 'gl', vim.diagnostic.open_float,
                        { buffer = args.buf, desc = 'LSP: line diagnostics' })

                    -- Format on save for any server that provides formatting.
                    if client:supports_method('textDocument/formatting') then
                        vim.api.nvim_create_autocmd('BufWritePre', {
                            buffer = args.buf,
                            callback = function()
                                vim.lsp.buf.format({ bufnr = args.buf, id = client.id })
                            end
                        })
                    end
                end,
            })

            -- Per-server settings (registered before servers are enabled so they
            -- merge into the resolved config).
            vim.lsp.config('ts_ls', {
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
                        },
                        format = {
                            insertSpaceBeforeFunctionParenthesis = true,
                            insertSpaceAfterConstructor = true,
                        }
                    }
                }
            })

            vim.lsp.config('rust_analyzer', {
                settings = {
                    ['rust-analyzer'] = {
                        checkOnSave = true,
                        check = {
                            command = "clippy",
                        },
                        imports = {
                            granularity = {
                                group = "module",
                            },
                            prefix = "self",
                        },
                        cargo = {
                            buildScripts = {
                                enable = true,
                            },
                        },
                        procMacro = {
                            enable = true
                        },
                        inlayHints = {
                            bindingModeHints = { enable = true },
                            chainingHints = { enable = true },
                            closingBraceHints = { enable = true },
                            closureCaptureHints = { enable = true },
                            closureReturnTypeHints = { enable = "always" },
                            discriminantHints = { enable = "always" },
                            expressionAdjustmentHints = { enable = "always" },
                            implicitDrops = { enable = true },
                            lifetimeElisionHints = { enable = "always" },
                            parameterHints = { enable = true },
                            rangeExclusiveHints = { enable = true },
                            typeHints = { enable = true },
                        },
                        typing = {
                            autoClosingAngleBrackets = { enable = true }
                        }
                    }
                }
            })

            vim.lsp.config('lua_ls', {
                settings = {
                    Lua = {
                        diagnostics = {
                            globals = { 'vim' }
                        }
                    }
                }
            })

            -- nvim-lspconfig's terraformls config calls vim.lsp.codelens.enable(),
            -- which only exists on nvim 0.12+. On 0.11 that field is nil and
            -- on_attach throws ON_ATTACH_ERROR, so replace it with an equivalent
            -- that falls back to refreshing codelenses on the usual events.
            vim.lsp.config('terraformls', {
                on_attach = function(_, bufnr)
                    if vim.lsp.codelens.enable then
                        vim.lsp.codelens.enable(true, { bufnr = bufnr })
                        return
                    end
                    vim.api.nvim_create_autocmd(
                        { 'BufEnter', 'InsertLeave', 'BufWritePost' },
                        {
                            buffer = bufnr,
                            callback = function()
                                vim.lsp.codelens.refresh({ bufnr = bufnr })
                            end,
                        }
                    )
                    vim.lsp.codelens.refresh({ bufnr = bufnr })
                end,
            })

            vim.lsp.config('yamlls', {
                settings = {
                    yaml = {
                        schemas = {
                            ["https://json.schemastore.org/github-workflow.json"] =
                            ".github/workflows/*.yaml"
                        }
                    }
                }
            })

            -- Python: settings are ready, but pyright is not in ensure_installed
            -- (matching the previous setup, where no Python server was active).
            -- Add "pyright" to ensure_installed below to activate it.
            vim.lsp.config('pyright', {
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

            require('mason-lspconfig').setup({
                ensure_installed = {
                    "bashls",
                    "cssls",
                    "dockerls",
                    "eslint",
                    "golangci_lint_ls",
                    "jsonls",
                    "html",
                    "lua_ls",
                    "sqls",
                    "taplo",
                    "terraformls",
                    "templ",
                    "ts_ls",
                    "yamlls",
                    "zls",
                    "superhtml",
                },
            })

            require('go').setup {
                gofmt = 'golines',
                goimports = 'golines',
                max_line_len = 120,
                diagnostic = false,
                remap_commands = {
                    GoDoc = false,
                },
                lsp_cfg = {
                    settings = {
                        gopls = {
                            diagnosticsDelay = "1s",
                            diagnosticsTrigger = "Edit",
                            usePlaceholders = false,
                            semanticTokens = true,
                            directoryFilters = { "-vendor" },
                        }
                    },
                    capabilities = vim.tbl_deep_extend('force', capabilities, {
                        workspace = {
                            didChangeWatchedFiles = {
                                dynamicRegistration = true,
                            },
                        },
                    }),
                },
            }

            local format_sync_grp = vim.api.nvim_create_augroup("GoFormat", {})
            vim.api.nvim_create_autocmd("BufWritePre", {
                pattern = "*.go",
                callback = function()
                    require('go.format').gofmt()
                end,
                group = format_sync_grp,
            })

            vim.diagnostic.config({
                virtual_text = {
                    format = function(diagnostic)
                        -- Filter out "typecheck:" messages
                        if string.find(diagnostic.message, "typecheck:") then
                            return nil
                        end
                        return diagnostic.message
                    end,
                },
                signs = true,
                underline = true,
                severity_sort = true,
                update_in_insert = true,
            })

            vim.lsp.config('sourcekit', {
                cmd = { '/Library/Developer/CommandLineTools/usr/bin/sourcekit-lsp' },
                capabilities = {
                    workspace = {
                        didChangeWatchedFiles = {
                            dynamicRegistration = true,
                        },
                    },
                },
            })
            vim.lsp.enable('sourcekit')
        end
    }
}
