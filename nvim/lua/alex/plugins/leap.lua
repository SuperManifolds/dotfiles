return {
    {
        "ggandor/leap.nvim",
        config = function()
            require('leap').create_default_mappings()
            require('leap').opts.special_keys.prev_target = '<bs>'
            require('leap').opts.special_keys.prev_group = '<bs>'
        end
    }
}
