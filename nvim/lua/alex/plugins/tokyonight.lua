return {
    {
        "folke/tokyonight.nvim",
        lazy = false,
        priority = 1000,
        opts = {},
        config = function ()
  	        require("tokyonight").setup({
		        style = "night",
		        transparent = true,
		        dim_inactive = true,
		        styles = {
			        sidebars = "transparent",
                    comments = { italic = false },
                    keywords = { italic = false },
		            functions = { italic = false },
                },
                on_colors = function(colors)
                    colors.fg = "#fdfdfd"
                end,
                on_highlights = function (hl, c)
                    hl["CursorLineNr"] = { fg = "#56A8F5" }
                    hl["CursorLine"] = { link = "@none" }
                    hl["@lsp.type.namespace.go"] = { fg = "#60b3ab" }
                    hl["@lsp.type.namespace.rust"] = { fg = "#60b3ab" }
                    hl["typescriptImport"] = { fg = "#AB82F8" }
                    hl["typescriptExport"] = { fg = "#AB82F8" }

                    hl["Constant"] = { fg = "#EA7272" }
                    hl["Keyword"] = { fg = "#AB82F8" }
                    hl["rustStorage"] = { fg = "#AB82F8" }
                    hl["cInclude"] = { fg = "#AB82F8" }
                    
                    hl["@lsp.type.selfKeyword.rust"] = { fg = "#AB82F8" }
                    hl["typescriptIdentifier"] = { fg = "#AB82F8" }
                    hl["typescriptMethodAccessor"] = { fg = "#AB82F8" }
                    hl["cStructure"] = { fg = "#AB82F8" }
                    hl["typescriptNull"] = { fg = "#AB82F8" }
                    hl["cStorageClass"] = { fg = "#AB82F8" }
                    hl["Type"] = { fg = "#C77DBB" }
                    hl["@lsp.type.interface"] = { fg = "#C77DBB" }
                    hl["goBlock"] = { fg = "#999999" }
                    hl["goParen"] = { fg = "#999999" }
                    hl["rustSigil"] = { fg = "#999999" }
                    hl["Delimiter"] = { fg = "#999999" }
                    hl["@lsp.type.formatSpecifier.rust"] = { fg = "#999999" }
                    hl["@operator"] = { fg = "#999999" }
                    hl["Operator"] = { fg = "#999999" }
                    hl["rustDerive"] = { fg = "#999999" }
                    hl["typescriptBraces"] = { fg = "#999999" }
                    hl["typescriptAssign"] = { fg = "#999999" }
                    hl["typescriptProp"] = { fg = "#999999" }
                    hl["typescriptBinaryOp"] = { fg = "#999999" }
                    hl["typescriptTypeAnnotation"] = { fg = "#999999" }
                    hl["Function"] = { fg = "#56A8F5" }
                    hl["@lsp.typemod.member.declaration.typescript"] = { fg = "#56A8F5" }
                    hl["String"] = { fg = "#6AAB73" }
                    hl["@lsp.typemod.variable.static.rust"] = { fg = "#EA7272" }
                    hl["@lsp.mod.readonly.typescript"] = { fg = "#EA7272" }
                    hl["@lsp.typemod.variable.local.typescript"] = { fg = "#fdfdfd" }
                    hl["@lsp.typemod.function.defaultLibrary.go"] = { fg = "#FFC66D" }
                    hl["@lsp.typemod.macro.defaultLibrary.rust"] = { fg = "#FFC66D" }
                    hl["@lsp.typemod.method.defaultLibrary.rust"] = { fg = "#FFC66D" }
                    hl["@lsp.typemod.type.defaultLibrary"] = { fg = "#FFC66D" }
                    hl["@lsp.mod.defaultLibrary.typescript"] = { fg = "#FFC66D" }
                    hl["typescriptTypeReference"] = { fg = "#FFC66D" }
                    hl["@type.builtin"] = { fg = "#FFC66D" }
                    hl["cOperator"] = { fg = "#FFC66D" }
                    hl["rustDecNumber"] = { fg = "#FBF996" }
                    hl["typescriptNumber"] = { fg = "#FBF996" }

                    hl["@lsp.typemod.type.defaultLibrary.go"] = { fg = "#FFC66D" }
                    hl["@lsp.type.parameter.go"] = { link = "@none" }
                    hl["@lsp.type.parameter.typescript"] = { link = "@none" }
                    hl["@lsp.type.property.typescript"] = { link = "@none" }
                    hl["typescriptCall"] = { link = "@none" }
                    hl["@lsp.type.property.c"] = { link = "@none" }
                    hl["@variable.parameter"] = { link = "@none" }

                    hl["@lsp.mod.attribute.rust"] = { fg = "#b37d60" }
                    hl["@lsp.type.macro.rust"] = { fg = "#b37d60" }
                    hl["rustAttribute"] = { fg = "#b37d60" }
                    hl["rustMacro"] = { fg = "#b37d60" }
                    hl["cDefine"] = { fg = "#b37d60" }
                    hl["@lsp.type.macro.c"] = { fg = "#b37d60" }
                    hl["@lsp.type.enumMember.rust"] = { fg = "#70FC95" }
                    hl["@lsp.typemod.enum.declaration.rust"] = { fg = "#C77DBB" }
                    hl["@lsp.type.parameter.rust"] = { link = "@none" }
                    hl["@lsp.typemod.enum.library.rust"] = { fg = "#70FC95" }
                    hl["@lsp.typemod.enum.defaultLibrary.rust"] = { fg = "#70FC95" }
                    hl["@lsp.typemod.enumMember.library.rust"] = { fg = "#70FC95" }
                    hl["typescriptOptionalMark"] = { fg = "#70FC95" }
                    hl["@lsp.type.enumMember.typescript"] = { fg = "#70FC95" }
                    hl["@lsp.typemod.enumMember.readonly.typescript"] = { fg = "#70FC95" }
                    hl["goVar"] = { fg = "#70FC95" }
                    hl["typescriptMember"] = { link = "@none" }

                end
	        })
        end
    }
}
