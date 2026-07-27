return {
    {
        "catgoose/nvim-colorizer.lua", -- maintained fork of norcalli/nvim-colorizer.lua
        event = "BufReadPre",
        opts = {
            filetypes = { 'rust', 'css', 'html', 'javascript', 'typescript', 'dosini' },
            user_default_options = {
                RGB = true,
                RRGGBB = true,
                RRGGBBAA = true,
                rgb_fn = true, -- CSS rgb() and rgba()
                hsl_fn = true, -- CSS hsl() and hsla()
            },
        },
    }
}
