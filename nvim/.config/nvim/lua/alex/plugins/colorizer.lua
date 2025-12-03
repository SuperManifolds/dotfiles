return {
    {
        "norcalli/nvim-colorizer.lua",
        config = function()
            require 'colorizer'.setup({
                'rust',
                'css',
                'html',
                'javascript',
                'typescript',
            }, {
                RGB = true,
                RRGGBB = true,
                RRGGBBAA = true,
                rgb_fn = true,   -- CSS rgb() and rgba()
                hsl_fn = true,   -- CSS hsl() and hsla()
            })
        end
    }
}
