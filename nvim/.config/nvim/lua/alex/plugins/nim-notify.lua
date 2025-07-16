return {
    {
        "rcarriga/nvim-notify",
        commit = "29b33efc802a304b1cf13ab200915d4e9e67373d",
        config = function()
            vim.notify = require("notify")
        end
    }
}
