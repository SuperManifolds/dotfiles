return {
    {
        'saghen/blink.cmp',
        event = 'InsertEnter',
        dependencies = {
            { 'saghen/blink.lib' }, -- required by blink.cmp v2 (shared Lua library)
            { 'L3MON4D3/LuaSnip' },
        },
        opts = {
            -- Pure-Lua fuzzy matcher: no Rust binary to build/download. blink's
            -- Lua implementation is first-class; fast enough for LSP completion.
            fuzzy = { implementation = 'lua' },

            -- LuaSnip as the snippet engine (neogen/luasnip completions keep working).
            snippets = { preset = 'luasnip' },

            sources = {
                default = { 'lsp', 'path', 'snippets', 'buffer' },
            },

            -- Match the previous nvim-cmp behaviour: no item is preselected, and
            -- nothing is inserted until explicitly accepted.
            completion = {
                list = { selection = { preselect = false, auto_insert = false } },
                documentation = { auto_show = true },
                menu = { draw = { treesitter = { 'lsp' } } },
            },

            -- Keymap parity with the old nvim-cmp setup:
            --   <Tab>        accept the selected/first item (else fall through)
            --   <CR>/<C-y>   accept only when an item is selected
            --   <C-n>/<C-p>  select next/previous
            --   <C-u>/<C-d>  scroll docs
            --   <C-f>/<C-b>  jump forward/backward in a snippet (LuaSnip)
            --   <C-Space>    trigger / toggle docs   <C-e> dismiss
            keymap = {
                preset = 'none',
                ['<Tab>'] = { 'select_and_accept', 'fallback' },
                ['<CR>'] = { 'accept', 'fallback' },
                ['<C-y>'] = { 'select_and_accept' },
                ['<C-n>'] = { 'select_next', 'fallback' },
                ['<C-p>'] = { 'select_prev', 'fallback' },
                ['<C-u>'] = { 'scroll_documentation_up', 'fallback' },
                ['<C-d>'] = { 'scroll_documentation_down', 'fallback' },
                ['<C-f>'] = { 'snippet_forward', 'fallback' },
                ['<C-b>'] = { 'snippet_backward', 'fallback' },
                ['<C-Space>'] = { 'show', 'show_documentation', 'hide_documentation' },
                ['<C-e>'] = { 'hide', 'fallback' },
            },

            -- Nerd-font icons in the menu (matches the old lsp-zero cmp_format look).
            appearance = { nerd_font_variant = 'mono' },
        },
    },
}
