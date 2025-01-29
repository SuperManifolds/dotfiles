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

                    local best_candidate = data[#data] -- Default to last (deepest) symbol

                    if best_candidate.type == "Field" and #data > 1 then
                        for i = #data - 1, 1, -1 do
                            if data[i].type == "Struct" or data[i].type == "Class" then
                                best_candidate = data[i]
                                break
                            end
                        end
                    end

                    local line_number = best_candidate.scope.start.line
                    return string.format("    %%#BarbecueLineNumber#%d%%* ", line_number)
                end
            })
        end,
    }
}
