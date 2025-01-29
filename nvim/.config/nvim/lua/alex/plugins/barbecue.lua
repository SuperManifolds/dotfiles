return {
    {
        "utilyre/barbecue.nvim",
        name = "barbecue",
        version = "*",
        dependencies = {
            "SmiteshP/nvim-navic",
            "nvim-tree/nvim-web-devicons", -- optional dependency
        },
        config = function()
            vim.api.nvim_set_hl(0, "BarbecueLineNumber", { link = "CursorLineNr" })

            require("barbecue").setup({
                attach_navic = true,
                lead_custom_section = function()
                    local navic = require("nvim-navic")
                    local data = navic.get_data()

                    if not data or vim.tbl_isempty(data) then
                        return "       "
                    end

                    -- Get the deepest (last) symbol
                    local deepest_item = data[#data]
                    local line_number = deepest_item.scope.start.line

                    return string.format("    %%#BarbecueLineNumber#%d%%* ", line_number)
                end
            })
        end,
    }
}
